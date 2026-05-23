"""
API导入服务模块

支持从外部API定义文件自动生成性能测试任务配置，包括：
- 导入Swagger 2.0规范
- 导入OpenAPI 3.0规范
- 导入Postman Collection（v2.1）
- 解析API定义自动生成任务配置
"""

import json
from pathlib import Path
from typing import Any

from database.db_manager import DatabaseManager
from utils.logger import get_logger
from utils.helpers import load_json

logger = get_logger("api_import_service")


class ApiImportService:
    """API导入服务类

    解析Swagger/OpenAPI和Postman Collection格式的API定义文件，
    自动提取接口信息并生成性能测试任务配置。
    """

    def __init__(self, db: DatabaseManager | None = None) -> None:
        """初始化API导入服务

        Args:
            db: 数据库管理器实例，为None时使用单例
        """
        self._db = db or DatabaseManager()

    def import_swagger(self, file_path: str | Path) -> list[dict[str, Any]]:
        """导入Swagger/OpenAPI规范文件

        自动检测规范版本（Swagger 2.0 或 OpenAPI 3.0），
        解析API定义并生成对应的任务配置列表。

        Args:
            file_path: Swagger/OpenAPI JSON文件路径

        Returns:
            生成的任务信息列表

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误或不支持的规范版本
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        spec = load_json(file_path)
        if spec is None:
            raise ValueError(f"无法解析JSON文件: {file_path}")

        swagger_version = spec.get("swagger", "")
        openapi_version = spec.get("openapi", "")

        if swagger_version.startswith("2"):
            logger.info("检测到Swagger 2.0规范，版本=%s", swagger_version)
            task_configs = self._parse_swagger_2(spec)
        elif openapi_version.startswith("3"):
            logger.info("检测到OpenAPI 3.0规范，版本=%s", openapi_version)
            task_configs = self._parse_openapi_3(spec)
        else:
            raise ValueError(
                f"不支持的API规范版本: swagger={swagger_version}, openapi={openapi_version}，"
                f"仅支持Swagger 2.0和OpenAPI 3.0"
            )

        tasks: list[dict[str, Any]] = []
        for config in task_configs:
            try:
                from services.task_service import TaskService
                task_svc = TaskService(self._db)
                task = task_svc.create_task(config)
                tasks.append(task)
            except Exception as e:
                logger.error("创建导入任务失败，接口=%s: %s", config.get("name", ""), e)

        logger.info(
            "Swagger/OpenAPI导入完成，文件=%s，解析接口=%d，成功创建=%d",
            file_path,
            len(task_configs),
            len(tasks),
        )
        return tasks

    def import_postman(self, file_path: str | Path) -> list[dict[str, Any]]:
        """导入Postman Collection文件

        解析Postman Collection v2.1格式的JSON文件，
        提取请求信息并生成任务配置。

        Args:
            file_path: Postman Collection JSON文件路径

        Returns:
            生成的任务信息列表

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件格式错误
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        data = load_json(file_path)
        if data is None:
            raise ValueError(f"无法解析JSON文件: {file_path}")

        info = data.get("info", {})
        collection_name = info.get("name", "Postman Import")
        schema = info.get("schema", "")

        logger.info("导入Postman Collection: %s, schema=%s", collection_name, schema)

        task_configs = self._parse_postman_items(data.get("item", []), collection_name)

        tasks: list[dict[str, Any]] = []
        for config in task_configs:
            try:
                from services.task_service import TaskService
                task_svc = TaskService(self._db)
                task = task_svc.create_task(config)
                tasks.append(task)
            except Exception as e:
                logger.error("创建导入任务失败，接口=%s: %s", config.get("name", ""), e)

        logger.info(
            "Postman Collection导入完成，文件=%s，解析请求=%d，成功创建=%d",
            file_path,
            len(task_configs),
            len(tasks),
        )
        return tasks

    def _parse_swagger_2(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """解析Swagger 2.0规范

        遍历paths对象中的所有路径和方法，
        提取接口信息并转换为任务配置格式。

        Args:
            spec: Swagger 2.0规范字典

        Returns:
            任务配置字典列表
        """
        task_configs: list[dict[str, Any]] = []
        base_url = self._build_base_url_swagger2(spec)
        paths = spec.get("paths", {})
        definitions = spec.get("definitions", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method, operation in path_item.items():
                if method.lower() not in ("get", "post", "put", "delete", "patch", "head", "options"):
                    continue
                if not isinstance(operation, dict):
                    continue

                operation_id = operation.get("operationId", "")
                summary = operation.get("summary", "")
                name = operation_id or summary or f"{method.upper()} {path}"

                headers = self._extract_swagger2_headers(operation)
                query_params = self._extract_swagger2_params(operation, "query")
                body = self._extract_swagger2_body(operation, definitions)

                config: dict[str, Any] = {
                    "name": name,
                    "type": "HTTP",
                    "method": method.upper(),
                    "url": base_url,
                    "headers": headers,
                    "params": query_params,
                    "body": body,
                    "body_type": "json" if body else "none",
                    "users": 10,
                    "spawn_rate": 1,
                    "run_time": "5m",
                    "timeout": 30,
                }
                task_configs.append(config)

        return task_configs

    def _parse_openapi_3(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        """解析OpenAPI 3.0规范

        遍历paths对象中的所有路径和方法，
        提取接口信息并转换为任务配置格式。
        支持components/schemas引用解析。

        Args:
            spec: OpenAPI 3.0规范字典

        Returns:
            任务配置字典列表
        """
        task_configs: list[dict[str, Any]] = []
        base_url = self._build_base_url_openapi3(spec)
        paths = spec.get("paths", {})
        components = spec.get("components", {})

        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            for method, operation in path_item.items():
                if method.lower() not in ("get", "post", "put", "delete", "patch", "head", "options"):
                    continue
                if not isinstance(operation, dict):
                    continue

                operation_id = operation.get("operationId", "")
                summary = operation.get("summary", "")
                name = operation_id or summary or f"{method.upper()} {path}"

                headers = self._extract_openapi3_headers(operation)
                query_params = self._extract_openapi3_params(operation, "query")
                body = self._extract_openapi3_body(operation, components)

                config: dict[str, Any] = {
                    "name": name,
                    "type": "HTTP",
                    "method": method.upper(),
                    "url": base_url,
                    "headers": headers,
                    "params": query_params,
                    "body": body,
                    "body_type": "json" if body else "none",
                    "users": 10,
                    "spawn_rate": 1,
                    "run_time": "5m",
                    "timeout": 30,
                }
                task_configs.append(config)

        return task_configs

    def _parse_postman_items(
        self,
        items: list[dict[str, Any]],
        parent_name: str = "",
    ) -> list[dict[str, Any]]:
        """递归解析Postman Collection中的请求项

        Postman Collection支持嵌套文件夹结构，
        此方法递归遍历所有层级提取请求信息。

        Args:
            items: Postman Collection的item列表
            parent_name: 父级文件夹名称

        Returns:
            任务配置字典列表
        """
        task_configs: list[dict[str, Any]] = []

        for item in items:
            if not isinstance(item, dict):
                continue

            item_name = item.get("name", "Unnamed")

            if "item" in item:
                sub_configs = self._parse_postman_items(item["item"], item_name)
                task_configs.extend(sub_configs)
                continue

            request = item.get("request")
            if not isinstance(request, dict):
                continue

            config = self._parse_postman_request(request, item_name, parent_name)
            if config:
                task_configs.append(config)

        return task_configs

    def _parse_postman_request(
        self,
        request: dict[str, Any],
        item_name: str,
        folder_name: str,
    ) -> dict[str, Any] | None:
        """解析单个Postman请求

        提取请求的URL、方法、请求头、请求体等信息，
        转换为任务配置格式。

        Args:
            request: Postman请求对象
            item_name: 请求名称
            folder_name: 所属文件夹名称

        Returns:
            任务配置字典，解析失败返回None
        """
        method = request.get("method", "GET").upper()

        url_obj = request.get("url", {})
        if isinstance(url_obj, str):
            url = url_obj
        elif isinstance(url_obj, dict):
            raw = url_obj.get("raw", "")
            host = url_obj.get("host", [])
            path = url_obj.get("path", [])
            if raw:
                url = raw
            elif host:
                host_str = ".".join(host) if isinstance(host, list) else str(host)
                protocol = url_obj.get("protocol", "https")
                path_str = "/".join(path) if isinstance(path, list) else str(path)
                url = f"{protocol}://{host_str}/{path_str}"
            else:
                url = ""
        else:
            url = ""

        if not url:
            logger.warning("Postman请求缺少URL，跳过: %s", item_name)
            return None

        headers: dict[str, str] = {}
        header_list = request.get("header", [])
        if isinstance(header_list, list):
            for h in header_list:
                if isinstance(h, dict) and not h.get("disabled", False):
                    key = h.get("key", "")
                    value = h.get("value", "")
                    if key:
                        headers[key] = value

        query_params: dict[str, str] = {}
        query_list = url_obj.get("query", []) if isinstance(url_obj, dict) else []
        if isinstance(query_list, list):
            for q in query_list:
                if isinstance(q, dict) and not q.get("disabled", False):
                    key = q.get("key", "")
                    value = q.get("value", "")
                    if key:
                        query_params[key] = value

        body = {}
        body_type = "none"
        body_obj = request.get("body", {})
        if isinstance(body_obj, dict):
            body_mode = body_obj.get("mode", "")
            if body_mode == "raw":
                raw_content = body_obj.get("raw", "")
                raw_options = body_obj.get("options", {})
                raw_lang = ""
                if isinstance(raw_options, dict):
                    raw_lang = raw_options.get("raw", {}).get("language", "")

                if raw_lang == "json" or raw_content.strip().startswith("{"):
                    try:
                        body = json.loads(raw_content)
                        body_type = "json"
                    except (json.JSONDecodeError, TypeError):
                        body = {"raw": raw_content}
                        body_type = "raw"
                else:
                    body = {"raw": raw_content}
                    body_type = "raw"
            elif body_mode == "formdata":
                form_data = body_obj.get("formdata", [])
                if isinstance(form_data, list):
                    for fd in form_data:
                        if isinstance(fd, dict) and not fd.get("disabled", False):
                            key = fd.get("key", "")
                            value = fd.get("value", "")
                            if key:
                                body[key] = value
                body_type = "form"
            elif body_mode == "urlencoded":
                urlencoded = body_obj.get("urlencoded", [])
                if isinstance(urlencoded, list):
                    for ue in urlencoded:
                        if isinstance(ue, dict) and not ue.get("disabled", False):
                            key = ue.get("key", "")
                            value = ue.get("value", "")
                            if key:
                                body[key] = value
                body_type = "form"

        auth = request.get("auth", {})
        token = ""
        if isinstance(auth, dict):
            auth_type = auth.get("type", "")
            auth_items = auth.get(auth_type, [])
            if auth_type == "bearer" and isinstance(auth_items, list):
                for ai in auth_items:
                    if isinstance(ai, dict) and ai.get("key") == "token":
                        token = ai.get("value", "")

        prefix = f"{folder_name} - " if folder_name else ""
        return {
            "name": f"{prefix}{item_name}",
            "type": "HTTP",
            "method": method,
            "url": url,
            "headers": headers,
            "params": query_params,
            "body": body,
            "body_type": body_type,
            "token": token,
            "users": 10,
            "spawn_rate": 1,
            "run_time": "5m",
            "timeout": 30,
        }

    @staticmethod
    def _build_base_url_swagger2(spec: dict[str, Any]) -> str:
        """构建Swagger 2.0的基础URL

        从scheme、host和basePath字段拼接基础URL。

        Args:
            spec: Swagger 2.0规范字典

        Returns:
            基础URL字符串
        """
        schemes = spec.get("schemes", ["http"])
        scheme = schemes[0] if schemes else "http"
        host = spec.get("host", "localhost")
        base_path = spec.get("basePath", "")
        if base_path == "/":
            base_path = ""
        return f"{scheme}://{host}{base_path}"

    @staticmethod
    def _build_base_url_openapi3(spec: dict[str, Any]) -> str:
        """构建OpenAPI 3.0的基础URL

        从servers数组中提取第一个URL作为基础URL。

        Args:
            spec: OpenAPI 3.0规范字典

        Returns:
            基础URL字符串
        """
        servers = spec.get("servers", [])
        if servers:
            first_server = servers[0]
            if isinstance(first_server, dict):
                return first_server.get("url", "http://localhost")
            return str(first_server)
        return "http://localhost"

    @staticmethod
    def _extract_swagger2_headers(operation: dict[str, Any]) -> dict[str, str]:
        """从Swagger 2.0操作中提取请求头

        遍历parameters列表中in=header的参数，
        对于有默认值的参数填入默认值，否则填入占位符。

        Args:
            operation: Swagger 2.0操作对象

        Returns:
            请求头字典
        """
        headers: dict[str, str] = {}
        consumes = operation.get("consumes", [])
        if consumes:
            headers["Content-Type"] = consumes[0]

        for param in operation.get("parameters", []):
            if not isinstance(param, dict):
                continue
            if param.get("in") == "header":
                name = param.get("name", "")
                default = param.get("default", "")
                headers[name] = str(default) if default else f"{{{{{name}}}}}"

        return headers

    @staticmethod
    def _extract_swagger2_params(
        operation: dict[str, Any],
        param_in: str,
    ) -> dict[str, str]:
        """从Swagger 2.0操作中提取查询参数

        Args:
            operation: Swagger 2.0操作对象
            param_in: 参数位置（query/path等）

        Returns:
            参数字典
        """
        params: dict[str, str] = {}
        for param in operation.get("parameters", []):
            if not isinstance(param, dict):
                continue
            if param.get("in") == param_in:
                name = param.get("name", "")
                default = param.get("default", "")
                params[name] = str(default) if default else f"{{{{{name}}}}}"

        return params

    @staticmethod
    def _extract_swagger2_body(
        operation: dict[str, Any],
        definitions: dict[str, Any],
    ) -> dict[str, Any]:
        """从Swagger 2.0操作中提取请求体

        解析body参数的schema引用，生成示例请求体。

        Args:
            operation: Swagger 2.0操作对象
            definitions: Swagger 2.0的definitions字典

        Returns:
            请求体字典
        """
        for param in operation.get("parameters", []):
            if not isinstance(param, dict):
                continue
            if param.get("in") == "body":
                schema = param.get("schema", {})
                return ApiImportService._resolve_schema(schema, definitions)

        return {}

    @staticmethod
    def _extract_openapi3_headers(operation: dict[str, Any]) -> dict[str, str]:
        """从OpenAPI 3.0操作中提取请求头

        Args:
            operation: OpenAPI 3.0操作对象

        Returns:
            请求头字典
        """
        headers: dict[str, str] = {}
        for param in operation.get("parameters", []):
            if not isinstance(param, dict):
                continue
            if param.get("in") == "header":
                name = param.get("name", "")
                schema = param.get("schema", {})
                default = schema.get("default", "") if isinstance(schema, dict) else ""
                headers[name] = str(default) if default else f"{{{{{name}}}}}"

        return headers

    @staticmethod
    def _extract_openapi3_params(
        operation: dict[str, Any],
        param_in: str,
    ) -> dict[str, str]:
        """从OpenAPI 3.0操作中提取查询参数

        Args:
            operation: OpenAPI 3.0操作对象
            param_in: 参数位置

        Returns:
            参数字典
        """
        params: dict[str, str] = {}
        for param in operation.get("parameters", []):
            if not isinstance(param, dict):
                continue
            if param.get("in") == param_in:
                name = param.get("name", "")
                schema = param.get("schema", {})
                default = schema.get("default", "") if isinstance(schema, dict) else ""
                params[name] = str(default) if default else f"{{{{{name}}}}}"

        return params

    @staticmethod
    def _extract_openapi3_body(
        operation: dict[str, Any],
        components: dict[str, Any],
    ) -> dict[str, Any]:
        """从OpenAPI 3.0操作中提取请求体

        解析requestBody的content/schema引用，生成示例请求体。

        Args:
            operation: OpenAPI 3.0操作对象
            components: OpenAPI 3.0的components字典

        Returns:
            请求体字典
        """
        request_body = operation.get("requestBody", {})
        if not isinstance(request_body, dict):
            return {}

        content = request_body.get("content", {})
        if not isinstance(content, dict):
            return {}

        json_content = content.get("application/json", {})
        if not isinstance(json_content, dict):
            return {}

        schema = json_content.get("schema", {})
        if not isinstance(schema, dict):
            return {}

        schemas = components.get("schemas", {}) if isinstance(components, dict) else {}
        return ApiImportService._resolve_schema(schema, schemas)

    @staticmethod
    def _resolve_schema(
        schema: dict[str, Any],
        definitions: dict[str, Any],
        depth: int = 0,
    ) -> dict[str, Any]:
        """递归解析Schema引用，生成示例数据

        支持$ref引用解析、基本类型默认值生成、
        嵌套对象和数组的递归解析。
        限制最大递归深度防止循环引用。

        Args:
            schema: Schema字典
            definitions: 定义字典（Swagger 2.0的definitions或OpenAPI 3.0的schemas）
            depth: 当前递归深度

        Returns:
            示例数据字典
        """
        if depth > 5:
            return {}

        if "$ref" in schema:
            ref_path = schema["$ref"]
            ref_name = ref_path.split("/")[-1]
            ref_schema = definitions.get(ref_name, {})
            if isinstance(ref_schema, dict):
                return ApiImportService._resolve_schema(ref_schema, definitions, depth + 1)
            return {}

        schema_type = schema.get("type", "object")

        if schema_type == "object":
            result: dict[str, Any] = {}
            properties = schema.get("properties", {})
            if isinstance(properties, dict):
                for prop_name, prop_schema in properties.items():
                    if not isinstance(prop_schema, dict):
                        continue
                    if "default" in prop_schema:
                        result[prop_name] = prop_schema["default"]
                    elif "example" in prop_schema:
                        result[prop_name] = prop_schema["example"]
                    else:
                        result[prop_name] = ApiImportService._get_default_value(
                            prop_schema, definitions, depth
                        )
            return result

        if schema_type == "array":
            items = schema.get("items", {})
            if isinstance(items, dict):
                return [ApiImportService._resolve_schema(items, definitions, depth + 1)]
            return []

        return ApiImportService._get_default_value(schema, definitions, depth)

    @staticmethod
    def _get_default_value(
        schema: dict[str, Any],
        definitions: dict[str, Any],
        depth: int,
    ) -> Any:
        """根据Schema类型生成默认值

        Args:
            schema: Schema字典
            definitions: 定义字典
            depth: 当前递归深度

        Returns:
            类型对应的默认值
        """
        if "enum" in schema:
            return schema["enum"][0] if schema["enum"] else ""

        schema_type = schema.get("type", "string")

        if schema_type == "string":
            fmt = schema.get("format", "")
            if fmt == "date-time":
                return "2025-01-01T00:00:00Z"
            if fmt == "date":
                return "2025-01-01"
            if fmt == "email":
                return "user@example.com"
            if fmt == "uri" or fmt == "url":
                return "https://example.com"
            if fmt == "integer" or fmt == "int32" or fmt == "int64":
                return 0
            return ""

        if schema_type == "integer" or schema_type == "number":
            return 0

        if schema_type == "boolean":
            return False

        if schema_type == "array":
            return []

        if schema_type == "object":
            return ApiImportService._resolve_schema(schema, definitions, depth + 1)

        if "$ref" in schema:
            return ApiImportService._resolve_schema(schema, definitions, depth + 1)

        return ""
