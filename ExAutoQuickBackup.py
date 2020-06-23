# coding: utf8

import copy
import itertools
import json
import os
import re
import shutil
import time
import traceback
from collections import deque
from enum import Enum, auto
from threading import Lock, Thread
from typing import *

import ruamel.yaml as yaml

from utils import constant, tool
from utils.info import Info
from utils.rtext import *
from utils.server_interface import ServerInterface

# region 杂项


class FakeInfo(NamedTuple):
    '''提供与 MCDR 传入的 info 类似的接口'''
    isPlayer: bool = False
    is_player: bool = False
    player: str = '@a'


TIME_FORMAT = '%Y-%m-%d %H:%M:%S'


def format_time() -> str:
    return time.strftime(TIME_FORMAT, time.localtime())


def parse_time(t: str) -> float:
    return time.mktime(time.strptime(t, TIME_FORMAT))


def print_message(server: ServerInterface, info: Info, msg, tell=True, prefix='[EQB] '):
    msg = prefix + msg
    if info.is_player and not tell:
        server.say(msg)
    else:
        server.reply(info, msg)


def command_run(message, text, command):
    return RText(message).set_hover_text(text).set_click_event(RAction.run_command, command)


def print_waiting(server: ServerInterface, info: Info):
    print_message(server, info, '等待其他任务完成...')


# endregion

# region 配置


# 默认配置项
DEFAULT_CONFIG = {
    'Enable': True,
    'SizeDisplay': True,
    'SlotCount': 10,
    'Prefix': '!!eqb',
    'BackupPath': './ex_auto_qb_multi',
    'TurnOffAutoSave': True,
    'IgnoreSessionLock': True,
    'Strategy': 'default',
    'StrategyConfig': ['10min', '1h', '3h', '1d', '2d', '3d', '5d', '10d', '1M', '2M'],
    'WorldNames': [
        'world',
    ],
    # 0:guest 1:user 2:helper 3:admin
    'MinimumPermissionLevel': {
        'help': 0,
        'enable': 2,
        'disable': 2,
        'slot': 2,
        'back': 2,
        'confirm': 1,
        'abort': 1,
        'list': 0,
        'del': 2
    },
    'OverwriteBackupFolder': 'overwrite',
    'ServerPath': './server'
}

CONFIG_FILE_DIR = './config/'
CONFIG_FILE_NAME = os.path.join(CONFIG_FILE_DIR, 'ex_auto_quick_backup.yml')

config = copy.deepcopy(DEFAULT_CONFIG)


def save_default_config():
    global config
    config = copy.deepcopy(DEFAULT_CONFIG)
    write_config()


def read_config():
    global config
    os.makedirs(CONFIG_FILE_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE_NAME):
        save_default_config()
        return
    with open(CONFIG_FILE_NAME, 'r', encoding='UTF-8') as rf:
        try:
            config = yaml.safe_load(rf)
        except yaml.YAMLError:
            save_default_config()


def write_config():
    os.makedirs(CONFIG_FILE_DIR, exist_ok=True)
    with open(CONFIG_FILE_NAME, 'w', encoding='UTF-8') as wf:
        yaml.dump(config, wf, default_flow_style=False, allow_unicode=True)

# endregion

# region 任务管理


class TaskType(Enum):
    BACKUP = auto()
    RESTORE = auto()
    DELETE = auto()
    LIST = auto()
    SET_CONFIG = auto()

    def __str__(self):
        TASK_NAMES: Dict[TaskType, str] = {
            TaskType.BACKUP: '§a备份§r',
            TaskType.RESTORE: '§c回档§r',
            TaskType.DELETE: '§c删除§r',
            TaskType.LIST: '§b显示信息§r',
            TaskType.SET_CONFIG: '§c调整设置§r',
        }

        return TASK_NAMES[self]


class ActiveTask:
    '''任务调度器，保护备份文件夹、config 变量等。'''

    def __init__(self):
        self._lock = Lock()
        self._registry_lock = Lock()
        self._registry: Deque[Tuple[TaskType, int]] = deque()
        self._index = 0

    def register(self, task: TaskType, wait_for: List[TaskType] = [], wait_callback: Callable[[], Any] = lambda: None) -> Tuple[bool, Optional[TaskType]]:
        with self._registry_lock:
            for t, _ in self._registry:
                if t not in wait_for:
                    return (False, t)

            i = self._index
            self._registry.append((task, i))
            self._index += 1

            if len(self._registry) == 1:
                self._lock.acquire()
                return (True, None)

        wait_callback()
        time.sleep(0.01)

        while True:
            with self._registry_lock:
                if self._registry[0][1] == i:
                    self._lock.acquire()
                    return (True, None)

            time.sleep(0.01)

    def unregister(self):
        with self._registry_lock:
            self._registry.popleft()
            self._lock.release()


active_task = ActiveTask()

# endregion

# region 一般全局变量


slot_selected: Optional[int] = None
abort_restore = False
game_saved = False
plugin_unloaded = False

# endregion

# region 带单位的时间解析

TIME_UNITS = {
    'min': 1,
    'h': 60,
    'd': 24 * 60,
    'M': 30 * 24 * 60,
    'Y': 365 * 24 * 60
}
TIME_REGEX = re.compile(
    '^(\\d+(\\.\\d+)?)({})?$'.format('|'.join(TIME_UNITS.keys())), re.RegexFlag.IGNORECASE)


def time_length_to_seconds(x: Union[int, float, str]) -> float:
    if type(x) is int or type(x) is float:
        return x * 60.0
    else:
        match = re.match(TIME_REGEX, x)
        if not match:
            raise ValueError("Invalid string argument")
        multiplier = TIME_UNITS[match[3]] if match[3] is not None else 1
        return float(match[1]) * multiplier * 60

# endregion

# region 策略


class Strategy:
    def interval(self) -> float:
        return NotImplemented

    def decide_which_to_keep(self, ages: List[float]) -> List[bool]:
        return NotImplemented


class DefaultStrategy(Strategy):
    EPS = 10

    def __init__(self, server: ServerInterface, config: List[Union[int, float, str]]):
        try:
            self.config = sorted(map(time_length_to_seconds, config))
        except ValueError:
            pass

    def interval(self) -> float:
        return self.config[0]

    def decide_which_to_keep(self, ages: List[float]) -> List[bool]:
        result = [True] * len(ages)

        if len(ages) < len(self.config):
            return result

        for i in range(len(self.config) - 1):
            if ages[i + 1] + DefaultStrategy.EPS < self.config[i + 1]:
                result[i] = False
                return result

        return result


STRATEGIES: Dict[str, Callable[[ServerInterface, Any], Strategy]] = {
    'default': DefaultStrategy
}
strategy: Strategy


def init_strategy(server: ServerInterface, info: Info):
    global strategy
    try:
        if config['Strategy'] not in STRATEGIES:
            print_message(server, info, '策略\'{}\'不存在，此插件将被禁用')
            config['Strategy']

        strategy_factory = STRATEGIES[config['Strategy']]
        strategy = strategy_factory(server, config['StrategyConfig'])
    except:
        # 禁用自己
        server.disable_plugin(os.path.basename(__file__)[:-3])

        traceback.print_exc()
        print_message(server, info, '初始化策略失败，错误代码：' +
                      traceback.format_exc())

        raise

# endregion

# region 以世界为单位的文件操作


def copy_worlds(src_folder: str, dst_folder: str):
    def filter_ignore(path, files):
        return [file for file in files if file == 'session.lock' and config['IgnoreSessionLock']]
    for world in config['WorldNames']:
        shutil.copytree('{}/{}'.format(src_folder, world),
                        '{}/{}'.format(dst_folder, world), ignore=filter_ignore)


def remove_worlds(folder: str):
    for world in config['WorldNames']:
        shutil.rmtree('{}/{}'.format(folder, world))

# endregion

# region 槽位信息


class SlotInfo(TypedDict):
    time: str
    comment: str


slots: Dict[int, SlotInfo] = {}


def get_slot_folder(slot: int) -> str:
    return '{}/slot{}'.format(config['BackupPath'], slot)


def get_slot_info(slot: int) -> Optional[SlotInfo]:
    try:
        with open('{}/info.json'.format(get_slot_folder(slot))) as f:
            info = json.load(f, encoding='utf8')
        # for key in info.keys():
        #     value = info[key]
        return info
    except:
        return None


def format_slot_info(info_dict: Optional[SlotInfo] = None, slot_number: Optional[int] = None) -> Optional[str]:
    if type(info_dict) is dict:
        info = info_dict
    elif type(slot_number) is int:
        info = get_slot_info(slot_number)
    else:
        return None

    if info is None:
        return None
    msg = '日期: {}; 注释: {}'.format(info['time'], info.get('comment', '§7空§r'))
    return msg


def slot_number_formatter(slot: Union[int, str]) -> Optional[int]:
    if type(slot) is int:
        slot_number = slot
    else:
        try:
            slot_number = int(slot)
        except ValueError:
            return None
    if not 1 <= slot <= config['SlotCount']:
        return None
    return slot_number


def slot_check(server: ServerInterface, info: Info, slot: Union[int, str]) -> Optional[Tuple[int, SlotInfo]]:
    slot_number = slot_number_formatter(slot)
    if slot_number is None:
        print_message(server, info, '槽位输入错误，应输入一个位于[{}, {}]的数字'.format(
            1, config['SlotCount']))
        return None

    slot_info = get_slot_info(slot_number)
    if slot_info is None:
        print_message(server, info, '槽位输入错误，槽位§6{}§r为空'.format(slot_number))
        return None
    return slot_number, slot_info


def read_slots(server: ServerInterface, info: Info):
    global slots
    os.makedirs(config['BackupPath'], exist_ok=True)
    for i in range(1, config['SlotCount'] + 1):
        folder = get_slot_folder(i)
        if os.path.exists(folder):
            try:
                with open(os.path.join(folder, 'info.json'), 'r', encoding='UTF-8') as f:
                    slots[i] = json.load(f)
            except:
                print_message(server, info, '读取槽位{}的信息失败'.format(i))

# endregion

# region 备份操作及有关备份的命令处理


def delete_backup(server: ServerInterface, info: Info, slot: Union[int, str]):
    acquired, other_task = active_task.register(TaskType.DELETE, [
                                                TaskType.LIST, TaskType.SET_CONFIG], lambda: print_waiting(server, info))
    if not acquired:
        print_message(server, info, '§4有未完成的{}任务，删除取消§r'.format(other_task))
        return

    try:
        ret = slot_check(server, info, slot)
        if ret is None:
            return
        slot_number = ret[0]
        shutil.rmtree(get_slot_folder(slot_number))
    except Exception as e:
        traceback.print_exc()
        print_message(server, info, RText(
            '§4删除失败§r，详细错误信息请查看服务端后台').set_hover_text(e), tell=False)
    else:
        print_message(server, info, '§a删除完成§r', tell=False)
    finally:
        active_task.unregister()


def create_backup(server: ServerInterface, info: Info) -> Optional[SlotInfo]:
    '''仅负责备份到 1 号槽位，不负责管理其他备份。'''
    turn_off_auto_save = config['TurnOffAutoSave']
    slot_path = get_slot_folder(1)
    try:
        os.makedirs(slot_path, exist_ok=True)

        # start backup
        global game_saved, plugin_unloaded
        game_saved = False
        if turn_off_auto_save:
            server.execute('save-off')
        server.execute('save-all')
        while True:
            time.sleep(0.01)
            if game_saved:
                break
            if plugin_unloaded:
                server.reply(info, '插件重载，§a备份§r中断！')
                return None

        copy_worlds(config['ServerPath'], slot_path)

        slot_info = SlotInfo(time=format_time(), comment='自动保存')
        with open('{}/info.json'.format(slot_path), 'w') as f:
            json.dump(slot_info, f, indent=4)

        return slot_info
    except Exception as e:
        print_message(server, info, '§a备份§r失败，错误代码{}'.format(e))
        return None
    finally:
        if turn_off_auto_save:
            server.execute('save-on')


def schedule_backup(server: ServerInterface, info: Info):
    def get_slot_ages() -> Tuple[List[float], List[int]]:
        '''将槽位存在的时长从小到大排列，并给出对应的编号'''
        ages_with_index = ((slots[n]['time'], n) for n in slots)
        ages_with_index = ((start_time - parse_time(t), n)
                           for t, n in ages_with_index)
        ages_with_index = sorted(ages_with_index)
        ages = [a for a, _ in ages_with_index]
        indices = [i for _, i in ages_with_index]
        return (ages, indices)

    acquired, _ = active_task.register(TaskType.BACKUP, [
                                       TaskType.BACKUP, TaskType.RESTORE, TaskType.DELETE, TaskType.LIST, TaskType.SET_CONFIG])
    assert acquired

    print_message(server, info, '§a备份§r中...请稍等')
    start_time = time.time()

    try:
        ages, indices = get_slot_ages()
        keep = strategy.decide_which_to_keep(ages)

        slot_count = config['SlotCount']
        if sum(keep) < slot_count:
            slots_to_keep = frozenset(
                n for i, n in enumerate(indices) if keep[i])
        else:
            # 此时前 slot_count 个槽位应该都存在
            # 删除编号最大的槽位（理应是最老的），即保留其他槽位
            slots_to_keep = range(1, slot_count)

        # 找到最小的不保留 / 不存在的槽位编号，之前的槽位顺次后移
        min_unused_slot = next(itertools.dropwhile(
            lambda n: n in slots_to_keep, itertools.count(1)))
        if min_unused_slot in slots:
            shutil.rmtree(get_slot_folder(min_unused_slot))
            del slots[min_unused_slot]
        for i in range(min_unused_slot, 1, -1):
            shutil.move(get_slot_folder(i - 1), get_slot_folder(i))
            slots[i] = slots[i - 1]
            del slots[i - 1]

        slot_info = create_backup(server, info)

        if slot_info is None:
            return

        slots[1] = slot_info

        end_time = time.time()
        print_message(server, info, '§a备份§r完成，耗时§6{}§r秒'.format(
            round(end_time - start_time, 1)))
        print_message(server, info, format_slot_info(info_dict=slot_info))
    finally:
        active_task.unregister()


def restore_backup(server: ServerInterface, info: Info, slot_str: str):
    ret = slot_check(server, info, slot_str)
    if ret is None:
        return
    else:
        slot, slot_info = ret
    global slot_selected, abort_restore
    slot_selected = slot
    abort_restore = False
    print_message(server, info, '准备将存档恢复至槽位§6{}§r， {}'.format(
        slot, format_slot_info(info_dict=slot_info)))
    print_message(
        server, info,
        command_run('使用§7{0} confirm§r 确认§c回档§r'.format(
            config['Prefix']), '点击确认', '{0} confirm'.format(config['Prefix']))
        + ', '
        + command_run('§7{0} abort§r 取消'.format(
            config['Prefix']), '点击取消', '{0} abort'.format(config['Prefix']))
    )


def confirm_restore(server: ServerInterface, info: Info):
    acquired, current_task = active_task.register(
        TaskType.RESTORE, [TaskType.LIST, TaskType.SET_CONFIG])
    if not acquired:
        print_message(server, info, '正在{}，回档取消'.format(current_task))
        return

    try:
        global slot_selected
        if slot_selected is None:
            print_message(server, info, '没有什么需要确认的')
            return
        slot = slot_selected
        slot_selected = None

        print_message(server, info, '10秒后关闭服务器§c回档§r')
        for countdown in range(1, 10):
            print_message(server, info, command_run(
                '还有{}秒，将§c回档§r为槽位§6{}§r，{}'.format(
                    10 - countdown, slot, format_slot_info(slot_number=slot)),
                '点击终止回档！',
                '{} abort'.format(config['Prefix'])
            ))
            for i in range(10):
                time.sleep(0.1)
                global abort_restore
                if abort_restore:
                    print_message(server, info, '§c回档§r被中断！')
                    return

        server.stop()
        server.logger.info('[EQB] Wait for server to stop')
        server.wait_for_start()

        server.logger.info('[EQB] Backup current world to avoid idiot')
        overwrite_backup_path = os.path.join(
            config['BackupPath'], config['OverwriteBackupFolder'])
        if os.path.exists(overwrite_backup_path):
            shutil.rmtree(overwrite_backup_path)
        copy_worlds(config['ServerPath'], overwrite_backup_path)
        with open('{}/info.txt'.format(overwrite_backup_path), 'w') as f:
            f.write('Overwrite time: {}\n'.format(format_time()))
            f.write('Confirmed by: {}'.format(
                info.player if info.is_player else '$Console$'))

        slot_folder = get_slot_folder(slot)
        server.logger.info('[EQB] Deleting world')
        remove_worlds(config['ServerPath'])
        server.logger.info('[EQB] Restore backup ' + slot_folder)
        copy_worlds(slot_folder, config['ServerPath'])

        server.start()
    finally:
        active_task.unregister()


def trigger_abort(server: ServerInterface, info: Info):
    global abort_restore, slot_selected
    abort_restore = True
    slot_selected = None
    print_message(server, info, '终止操作！')


def list_backup(server: ServerInterface, info: Info, size_display=config['SizeDisplay']):
    def get_dir_size(dir):
        size = 0
        for root, dirs, files in os.walk(dir):
            size += sum([os.path.getsize(os.path.join(root, name))
                         for name in files])
        if size < 2 ** 30:
            return f'{round(size / 2 ** 20, 2)} MB'
        else:
            return f'{round(size / 2 ** 30, 2)} GB'

    acquired, _ = active_task.register(TaskType.LIST, [
                                       TaskType.BACKUP, TaskType.RESTORE, TaskType.DELETE, TaskType.LIST, TaskType.SET_CONFIG], lambda: print_waiting(server, info))
    assert acquired

    try:
        print_message(server, info, '§d【槽位信息】§r', prefix='')
        empty = True
        for i in range(1, config['SlotCount'] + 1):
            slot_info_str = format_slot_info(slot_number=i)
            if slot_info_str is None:
                continue
            empty = False
            print_message(
                server, info,
                RTextList(
                    f'[槽位§6{i}§r] ',
                    RText('[▷] ', color=RColor.green).h(f'点击回档至槽位§6{i}§r').c(
                        RAction.run_command, f'{config["Prefix"]} back {i}'),
                    RText('[×] ', color=RColor.red).h(f'点击删除槽位§6{i}§r').c(
                        RAction.suggest_command, f'{config["Prefix"]} del {i}'),
                    slot_info_str
                ),
                prefix=''
            )
        if empty:
            print_message(server, info, '§b(当前无备份)§r', prefix='')
        elif size_display:
            print_message(server, info, '备份总占用空间: §a{}§r'.format(
                get_dir_size(config['BackupPath'])), prefix='')
    finally:
        active_task.unregister()

# endregion

# region 无关备份的命令处理


HELP_MESSAGE = '''
------ MCDR Ex Auto Quick Backup 20200622 ------
一个支持多槽位的自动快速§a备份§r&§c回档§r插件，由§eQuickBackupM§r插件改编而来
§d【格式说明】§r
§7{0}§r 显示帮助信息
§7{0} help§r 显示帮助信息
§7{0} enable§r 启用自动备份，会强制进行一次备份
§7{0} disable§r 关闭自动备份
§7{0} slot §6<number>§r 调整槽位个数为 §6<number>§r 个
注意，若输入 §6<number>§r 小于当前槽位，不会导致真实槽位数的减小
减少的槽位仍在硬盘中存在，只是不会存在于列表中，也不会被新存档覆盖
§7{0} back §6[<slot>]§r §c回档§r为槽位§6<slot>§r的存档
当§6<slot>§r未被指定时默认选择槽位§61§r
§7{0} confirm§r 再次确认是否进行§c回档§r
§7{0} abort§r 在任何时候键入此指令可中断§c回档§r
§7{0} list§r 显示各槽位的存档信息
§7{0} del §6<slot>§r §c删除§r槽位§6<slot>§r的存档
'''.strip()


def print_help_message(server: ServerInterface, info: Info):
    if info.is_player:
        server.reply(info, '')
    for line in HELP_MESSAGE.format(config['Prefix']).splitlines():
        prefix = re.search(
            r'(?<=§7){}[\w ]*(?=§)'.format(config['Prefix']), line)
        if prefix is not None:
            print_message(server, info, RText(line).set_click_event(
                RAction.suggest_command, prefix.group()), prefix='')
        else:
            print_message(server, info, line, prefix='')
    list_backup(server, info, size_display=False)
    print_message(
        server, info,
        '§d【快捷操作】§r' + '\n' +
        RText('>>> §c点我回档至最近的备份§r <<<')
        .h('也就是回档至第一个槽位')
        .c(RAction.suggest_command, f'{config["Prefix"]} back'),
        prefix=''
    )


def set_config(server: ServerInterface, info: Info, key: str, value: Any, success_feedback='§a修改§r成功') -> bool:
    acquired, _ = active_task.register(TaskType.SET_CONFIG, [
                                       TaskType.BACKUP, TaskType.RESTORE, TaskType.DELETE, TaskType.LIST, TaskType.SET_CONFIG], lambda: print_waiting(server, info))
    assert acquired

    config[key] = value
    try:
        write_config()
    except Exception as e:
        traceback.print_exc()
        print_message(server, info, '§c修改§r保存失败.错误代码:' +
                      traceback.format_exc())
        print_message(server, info, '将重新读取配置')
        read_config()
        return False
    else:
        print_message(server, info, success_feedback)
        return True
    finally:
        active_task.unregister()


def enable(server: ServerInterface, info: Info):
    if config['Enable']:
        print_message(server, info, '§a插件功能§r已经是打开的')
        return

    set_config(server, info, 'Enable', True)


def disable(server: ServerInterface, info: Info):
    if not config['Enable']:
        print_message(server, info, '§a插件功能§r已经是关闭的')
        return

    set_config(server, info, 'Enable', False)


def slot(server: ServerInterface, info: Info, slot: str):
    slot_count = int(slot)
    if not 1 <= slot_count <= 1000:
        print_message(server, info, '输入不合法，允许的区间是§a[1, 1000]')
        return

    set_config(server, info, 'SlotCount', slot_count)

# endregion

# region 计时线程


class AutoSave(Thread):
    def __init__(self, server: ServerInterface):
        Thread.__init__(self)
        self.shutdown_flag = False
        self.server = server

    def run(self):
        while not self.shutdown_flag:
            time.sleep(strategy.interval())
            if self.shutdown_flag:
                return
            if config['Enable']:
                info: Any = FakeInfo()
                schedule_backup(self.server, info)

    def shutdown(self):
        self.shutdown_flag = True


autosave: AutoSave

# endregion

# region MCDR 钩子


def on_info(server: ServerInterface, info: Info):
    if not info.is_user:
        if info.content in ['Saved the game', 'Saved the world']:
            global game_saved
            game_saved = True
        return

    if tool.version_compare(constant.VERSION, '0.9.1-alpha') == -1:
        on_user_info(server, info)


def on_user_info(server: ServerInterface, info: Info):
    command = str(info.content).split()
    if len(command) == 0 or command[0] != config['Prefix']:
        return

    cmd_len = len(command)

    # MCDR permission check
    if cmd_len >= 2 and command[1] in config['MinimumPermissionLevel'].keys():
        if server.get_permission_level(info) < config['MinimumPermissionLevel'][command[1]]:
            print_message(server, info, '§c权限不足！§r')
            return

    # !!eqb
    if cmd_len == 1:
        print_help_message(server, info)

    # !!eqb help
    elif cmd_len == 2 and command[1] == 'help':
        print_help_message(server, info)

    # !!eqb enable
    elif cmd_len == 2 and command[1] == 'enable':
        enable(server, info)

    # !!eqb disable
    elif cmd_len == 2 and command[1] == 'disable':
        disable(server, info)

    # !!eqb slot <number>
    elif cmd_len == 3 and command[1] == 'slot':
        slot(server, info, command[2])

    # !!eqb back [<slot>]
    elif cmd_len in [2, 3] and command[1] == 'back':
        restore_backup(server, info, command[2] if cmd_len == 3 else '1')

    # !!eqb confirm
    elif cmd_len == 2 and command[1] == 'confirm':
        confirm_restore(server, info)

    # !!eqb abort
    elif cmd_len == 2 and command[1] == 'abort':
        trigger_abort(server, info)

    # !!eqb list
    elif cmd_len == 2 and command[1] == 'list':
        list_backup(server, info)

    # !!eqb del
    elif cmd_len == 3 and command[1] == 'del':
        delete_backup(server, info, command[2])

    else:
        print_message(server, info, command_run(
            '参数错误！请输入§7{}§r以获取插件信息'.format(config['Prefix']),
            '点击查看帮助',
            config['Prefix']
        ))


def on_load(server: ServerInterface, old):
    global active_task, autosave
    server.add_help_message(config['Prefix'], command_run(
        '全自动§a备份§r/§c回档§r，§6{}§r槽位'.format(config['SlotCount']), '点击查看帮助信息', config['Prefix']))

    if hasattr(old, 'active_task') and type(old.active_task) is type(active_task):
        active_task = old.active_task

    read_config()
    info: Any = FakeInfo()
    init_strategy(server, info)
    read_slots(server, info)

    autosave = AutoSave(server)
    autosave.start()


def on_unload(server: ServerInterface):
    global abort_restore, plugin_unloaded
    abort_restore = True
    plugin_unloaded = True
    autosave.shutdown()

# endregion
