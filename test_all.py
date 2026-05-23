import os
import sys
import tempfile
import shutil


def test_core():
    from config.settings import get_settings
    s = get_settings()
    assert s.theme in ('light', 'dark')
    assert s.thread_count >= 1
    s.theme = 'dark'
    assert s.theme == 'dark'
    s.theme = 'light'
    s.save()
    print('[PASS] Settings')

    from utils.logger import setup_logger, get_logger, set_log_level
    setup_logger()
    logger = get_logger('test')
    logger.info('test info')
    logger.warning('test warning')
    set_log_level('WARNING')
    set_log_level('INFO')
    print('[PASS] Logger')

    from utils.helpers import resource_path, ensure_dir, format_file_size, format_duration, save_json, load_json, write_csv, read_csv
    assert str(resource_path('test.txt')).endswith('test.txt')
    assert format_file_size(1024) == '1.00 KB'
    assert format_file_size(1048576) == '1.00 MB'
    assert format_duration(3665) == '1h1m5s'
    td = tempfile.mkdtemp()
    save_json(os.path.join(td, 't.json'), {'k': 'v'})
    assert load_json(os.path.join(td, 't.json'))['k'] == 'v'
    write_csv(os.path.join(td, 't.csv'), [{'n': 'a', 'v': '1'}, {'n': 'b', 'v': '2'}])
    rows = read_csv(os.path.join(td, 't.csv'))
    assert len(rows) == 2
    assert rows[0]['n'] == 'a'
    shutil.rmtree(td)
    print('[PASS] Helpers')

    from utils.system_monitor import SystemMonitor
    mon = SystemMonitor()
    cpu = mon.get_cpu_percent()
    mem = mon.get_memory_info()
    assert 0 <= cpu <= 100
    assert mem['percent'] > 0
    print(f'[PASS] SystemMonitor: CPU={cpu}%, MEM={mem["percent"]}%')

    from core.plugin_manager import PluginManager, PluginBase, HookType
    pm = PluginManager()
    class TP(PluginBase):
        @property
        def name(self): return 'tp'
        def on_load(self): pass
        def on_unload(self): pass
    pm.register_plugin(TP())
    assert 'tp' in pm._plugins
    pm.unregister_plugin('tp')
    print('[PASS] PluginManager')


def test_database():
    from database.db_manager import DatabaseManager
    db_path = os.path.join(tempfile.mkdtemp(), 'test.db')
    DatabaseManager.reset_instance()
    db = DatabaseManager(db_path=db_path)

    tid = db.create_task({
        'name': 'test_http', 'type': 'HTTP', 'method': 'GET',
        'url': 'http://example.com/api', 'headers': {'Content-Type': 'application/json'},
        'cookies': {'session': 'abc'}, 'token': 'Bearer test',
        'body': {}, 'body_type': 'json', 'file_path': '',
        'params': {'page': '1'}, 'csv_path': '',
        'users': 100, 'spawn_rate': 10, 'run_time': '5m',
        'timeout': 30, 'retry_count': 3
    })
    assert tid > 0
    task = db.get_task(tid)
    assert task is not None
    assert task['name'] == 'test_http'
    assert task['users'] == 100
    print('[PASS] DB create/get task')

    db.update_task(tid, {'name': 'updated', 'users': 200})
    u = db.get_task(tid)
    assert u['name'] == 'updated'
    assert u['users'] == 200
    print('[PASS] DB update task')

    rid = db.create_task_result({
        'task_id': tid, 'status': 'running', 'total_requests': 1000,
        'success_count': 950, 'fail_count': 50,
        'avg_response_time': 120.5, 'max_response_time': 500.0,
        'min_response_time': 10.0, 'p95_response_time': 300.0,
        'qps': 200.0, 'tps': 190.0, 'rps': 200.0, 'fail_rate': 5.0, 'current_users': 100
    })
    assert rid > 0
    r = db.get_task_result(rid)
    assert r['qps'] == 200.0
    print('[PASS] DB create/get result')

    hid = db.create_history({
        'task_id': tid, 'task_name': 'updated', 'duration': 300,
        'result_summary': 'done', 'stats_json': {'total': 1000}
    })
    assert hid > 0
    print('[PASS] DB create history')

    db.set_setting('k1', 'v1')
    assert db.get_setting('k1') == 'v1'
    print('[PASS] DB settings')

    nid = db.create_node({
        'task_id': tid, 'node_type': 'master', 'host': '127.0.0.1',
        'port': 5557, 'status': 'running', 'worker_count': 3
    })
    assert nid > 0
    print('[PASS] DB distributed_nodes')

    all_t = db.get_all_tasks()
    assert len(all_t) >= 1
    print('[PASS] DB list tasks')

    db.delete_task(tid)
    assert db.get_task(tid) is None
    print('[PASS] DB delete task (cascade)')

    db.close()
    DatabaseManager.reset_instance()
    shutil.rmtree(os.path.dirname(db_path))


def test_locust_engine():
    from core.locust_engine import LocustEngine, EngineConfig, TaskConfig, EngineState, substitute_variables, parse_run_time
    assert substitute_variables('${host}/api', {'host': 'http://localhost'}) == 'http://localhost/api'
    assert substitute_variables('no_vars', {}) == 'no_vars'
    print('[PASS] substitute_variables')

    assert parse_run_time('5m') == 300
    assert parse_run_time('1h') == 3600
    assert parse_run_time('30s') == 30
    assert parse_run_time('1h30m') == 5400
    assert parse_run_time('2h30m10s') == 9010
    print('[PASS] parse_run_time')

    config = EngineConfig(host='http://localhost:8080', users=50, spawn_rate=5, run_time='3m')
    assert config.users == 50
    assert config.run_time == '3m'
    print('[PASS] EngineConfig')

    tc = TaskConfig(name='test_api', method='GET', path='/api/users')
    assert tc.name == 'test_api'
    assert tc.method == 'GET'
    print('[PASS] TaskConfig')

    engine = LocustEngine(config)
    assert engine.state == EngineState.IDLE
    print('[PASS] LocustEngine init/state=IDLE')

    assert EngineState.RUNNING.value == 2
    assert EngineState.PAUSED.value == 3
    print('[PASS] EngineState enum')


def test_services():
    from services.task_service import TaskService
    from services.report_service import ReportService
    from services.scheduler_service import SchedulerService
    from services.api_import_service import ApiImportService
    print('[PASS] All services imported')

    ts = TaskService()
    errors = ts.validate_task({
        'name': '', 'type': 'HTTP', 'method': 'GET',
        'url': '', 'users': 0, 'spawn_rate': 0
    })
    assert len(errors) > 0
    print(f'[PASS] TaskService.validate_task: found {len(errors)} validation errors')

    errors2 = ts.validate_task({
        'name': 'valid_task', 'type': 'HTTP', 'method': 'GET',
        'url': 'http://example.com', 'users': 10, 'spawn_rate': 1
    })
    assert len(errors2) == 0
    print('[PASS] TaskService.validate_task: valid task passes')


def test_ui_imports():
    from ui.styles import StyleManager
    sm = StyleManager()
    light_qss = sm.get_qss('light')
    dark_qss = sm.get_qss('dark')
    assert len(light_qss) > 100
    assert len(dark_qss) > 100
    assert 'background' in light_qss
    assert 'background' in dark_qss
    print('[PASS] StyleManager: light/dark QSS generated')

    from ui.navigation import NavigationBar
    from ui.status_bar import SystemStatusBar
    from ui.main_window import MainWindow
    print('[PASS] UI modules imported')


def test_pages_imports():
    from pages.home_page import HomePage
    from pages.create_task_page import CreateTaskPage
    from pages.execute_task_page import ExecuteTaskPage
    from pages.monitor_page import MonitorPage
    from pages.history_page import HistoryPage
    from pages.settings_page import SettingsPage
    print('[PASS] All 6 pages imported')


if __name__ == '__main__':
    print('=' * 60)
    print('Locust压力测试平台 - 功能测试')
    print('=' * 60)

    tests = [
        ('核心模块', test_core),
        ('数据库模块', test_database),
        ('Locust引擎', test_locust_engine),
        ('服务层', test_services),
        ('UI模块', test_ui_imports),
        ('页面模块', test_pages_imports),
    ]

    passed = 0
    failed = 0
    for name, fn in tests:
        print(f'\n--- {name} ---')
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f'[FAIL] {name}: {e}')
            import traceback
            traceback.print_exc()
            failed += 1

    print('\n' + '=' * 60)
    print(f'测试结果: {passed} 通过, {failed} 失败')
    print('=' * 60)

    if failed > 0:
        sys.exit(1)
