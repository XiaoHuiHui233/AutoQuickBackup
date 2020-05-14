# coding: utf8
import os
import re
import shutil
import time
from threading import Lock, Thread
from utils.rtext import *
import ruamel.yaml as yaml
import json
import copy


'''默认配置项'''
config = {
    'Enable': True,
    'Interval': 5,
    'SizeDisplay': True,
    'SlotCount': 5,
    'Prefix': '!!aqb',
    'BackupPath': './auto_qb_multi',
    'TurnOffAutoSave': True,
    'IgnoreSessionLock': True,
    'WorldNames': [
        'world',
    ],
    # 0:guest 1:user 2:helper 3:admin
    'MinimumPermissionLevel': {
        'help': 1,
        'enable': 2,
        'disable': 2,
        'interval': 2,
        'slot': 2,
        'back': 2,
        'confirm': 1,
        'abort': 1,
        'list': 0,
    },
    'OverwriteBackupFolder': 'overwrite',
    'ServerPath': './server'
}

HelpMessage = '''
------ MCDR Auto Quick Backup 20200514 ------
一个支持多槽位的自动快速§a备份§r&§c回档§r插件，由§eQuickBackupM§r插件改编而来
§d【格式说明】§r
§7{0}§r 显示帮助信息
§7{0} help§r 显示帮助信息
§7{0} enable§r 启用自动备份，会强制进行一次备份
§7{0} disable§r 关闭自动备份
§7{0} interval §6<minutes>§r 设置自动备份的间隔时间为 §6<minutes>§r 分钟
§7{0} slot §6<number>§r 调整槽位个数为 §6<number>§r 个
注意，若输入 §6<number>§r 小于当前槽位，不会导致真实槽位数的减小
减少的槽位仍在硬盘中存在，只是不会存在于列表中，也不会被新存档覆盖
§7{0} back §6[<slot>]§r §c回档§r为槽位§6<slot>§r的存档
当§6<slot>§r未被指定时默认选择槽位§61§r
§7{0} confirm§r 再次确认是否进行§c回档§r
§7{0} abort§r 在任何时候键入此指令可中断§c回档§r
§7{0} list§r 显示各槽位的存档信息
'''.strip().format(config['Prefix'])
slot_selected = None
abort_restore = False
game_saved = False
plugin_unloaded = False
creating_backup = Lock()
restoring_backup = Lock()
'''
mcdr_root/
    MCDReforged.py
    server/
        world/
    auto_qb_multi/
        slot1/
            info.json
            world/
        slot2/
            ...
        ...
        overwrite/
            info.txt
            world/
    config/
        AutoQuickBackup/
            config.yml
'''

def saveDefaultConfig():
    yaml_dict = {
        'Enable': True,
        'Interval': 5,
        'SizeDisplay': True,
        'SlotCount': 5,
        'Prefix': '!!aqb',
        'BackupPath': './auto_qb_multi',
        'TurnOffAutoSave': True,
        'IgnoreSessionLock': True,
        'WorldNames': [
            'world',
        ],
        'MinimumPermissionLevel': {
            'help': 1,
            'enable': 2,
            'disable': 2,
            'interval': 2,
            'slot': 2,
            'back': 2,
            'confirm': 1,
            'abort': 1,
            'list': 0,
        },
        'OverwriteBackupFolder': 'overwrite',
        'ServerPath': './server',
    }
    with open('./config/AutoQuickBackup/config.yml', 'w', encoding='UTF-8') as wf:
        yaml.dump(yaml_dict, wf, default_flow_style=False, allow_unicode=True)
    config = copy.deepcopy(yaml_dict)


def read(server):
    if not os.path.exists('./config/AutoQuickBackup'):
        os.mkdirs('./config/AutoQuickBackup')
    if not os.path.exists('./config/AutoQuickBackup/config.yml'):
        saveDefaultConfig()
        return
    with open('./config/AutoQuickBackup/config.yml', 'r', encoding='UTF-8') as rf:
        try:
            config = yaml.safe_load(rf)
        except yaml.YAMLError as exc:
            saveDefaultConfig()

def write(server):
    if not os.path.exists('./config/AutoQuickBackup'):
        os.mkdirs('./config/AutoQuickBackup')
    with open('./config/AutoQuickBackup/config.yml', 'w', encoding='UTF-8') as wf:
        yaml.dump(config, wf, default_flow_style=False, allow_unicode=True)


def print_message(server, info, msg, tell=True, prefix='[AQB] '):
    msg = prefix + msg
    if info.is_player and not tell:
        server.say(msg)
    else:
        server.reply(info, msg)


def command_run(message, text, command):
    return RText(message).set_hover_text(text).set_click_event(RAction.run_command, command)


def copy_worlds(src, dst):
    def filter_ignore(path, files):
        return [file for file in files if file == 'session.lock' and config['IgnoreSessionLock']]
    for world in config['WorldNames']:
        shutil.copytree('{}/{}'.format(src, world), '{}/{}'.format(dst, world), ignore=filter_ignore)


def remove_worlds(folder):
    for world in config['WorldNames']:
        shutil.rmtree('{}/{}'.format(folder, world))


def get_slot_folder(slot):
    return '{}/slot{}'.format(config['BackupPath'], slot)


def get_slot_info(slot):
    try:
        with open('{}/info.json'.format(get_slot_folder(slot))) as f:
            info = json.load(f, encoding='utf8')
        for key in info.keys():
            value = info[key]
    except:
        info = None
    return info


def format_time():
    return time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())


def format_slot_info(info_dict=None, slot_number=None):
    if type(info_dict) is dict:
        info = info_dict
    elif type(slot_number) is not None:
        info = get_slot_info(slot_number)
    else:
        return None

    if info is None:
        return None
    msg = '日期: {}; 注释: {}'.format(info['time'], info.get('comment', '§7空§r'))
    return msg


def touch_backup_folder():
    def mkdir(path):
        if not os.path.exists(path):
            os.mkdir(path)

    mkdir(config['BackupPath'])
    for i in range(config['SlotCount']):
        mkdir(get_slot_folder(i + 1))


def slot_number_formater(slot):
    flag_fail = False
    if type(slot) is not int:
        try:
            slot = int(slot)
        except ValueError:
            flag_fail = True
    if flag_fail or not 1 <= slot <= config['SlotCount']:
        return None
    return slot


def slot_check(server, info, slot):
    slot = slot_number_formater(slot)
    if slot is None:
        print_message(server, info, '槽位输入错误，应输入一个位于[{}, {}]的数字'.format(1, config['SlotCount']))
        return None

    slot_info = get_slot_info(slot)
    if slot_info is None:
        print_message(server, info, '槽位输入错误，槽位§6{}§r为空'.format(slot))
        return None
    return slot, slot_info


def schedule_backup(server, info):
    global creating_backup
    acquired = creating_backup.acquire(blocking=False)
    if not acquired:
        print_message(server, info, '正在进行§a手动备份§r中，跳过本次自动备份。')
        return
    try:
        print_message(server, info, '§a备份§r中...请稍等')
        start_time = time.time()
        touch_backup_folder()

        # remove the last backup
        shutil.rmtree(get_slot_folder(config['SlotCount']))

        # move slot i-1 to slot i
        for i in range(config['SlotCount'], 1, -1):
            os.rename(get_slot_folder(i - 1), get_slot_folder(i))

        # start backup
        global game_saved, plugin_unloaded
        game_saved = False
        if config['TurnOffAutoSave']:
            server.execute('save-off')
        server.execute('save-all')
        while True:
            time.sleep(0.01)
            if game_saved:
                break
            if plugin_unloaded:
                server.reply(info, '插件重载，§a备份§r中断！')
                return
        slot_path = get_slot_folder(1)

        copy_worlds(config['ServerPath'], slot_path)
        slot_info = {'time': format_time()}
        slot_info['comment'] = '自动保存'
        with open('{}/info.json'.format(slot_path), 'w') as f:
            json.dump(slot_info, f, indent=4)
        end_time = time.time()
        print_message(server, info, '§a备份§r完成，耗时§6{}§r秒'.format(round(end_time - start_time, 1)))
        print_message(server, info, format_slot_info(info_dict=slot_info))
    except Exception as e:
        print_message(server, info, '§a备份§r失败，错误代码{}'.format(e))
    finally:
        creating_backup.release()
        if config['TurnOffAutoSave']:
            server.execute('save-on')


def restore_backup(server, info, slot):
    ret = slot_check(server, info, slot)
    if ret is None:
        return
    else:
        slot, slot_info = ret
    global slot_selected, abort_restore
    slot_selected = slot
    abort_restore = False
    print_message(server, info, '准备将存档恢复至槽位§6{}§r， {}'.format(slot, format_slot_info(info_dict=slot_info)))
    print_message(
        server, info,
        command_run('使用§7{0} confirm§r 确认§c回档§r'.format(config['Prefix']), '点击确认', '{0} confirm'.format(config['Prefix']))
        + ', '
        + command_run('§7{0} abort§r 取消'.format(config['Prefix']), '点击取消', '{0} abort'.format(config['Prefix']))
    )


def confirm_restore(server, info):
    global restoring_backup
    acquired = restoring_backup.acquire(blocking=False)
    if not acquired:
        print_message(server, info, '正在准备§c回档§r中，请不要重复输入')
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
                '还有{}秒，将§c回档§r为槽位§6{}§r，{}'.format(10 - countdown, slot, format_slot_info(slot_number=slot)),
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
        server.logger.info('[AQB] Wait for server to stop')
        server.wait_for_start()

        server.logger.info('[AQB] Backup current world to avoid idiot')
        overwrite_backup_path = config['BackupPath'] + '/' + config['OverwriteBackupFolder']
        if os.path.exists(overwrite_backup_path):
            shutil.rmtree(overwrite_backup_path)
        copy_worlds(config['ServerPath'], overwrite_backup_path)
        with open('{}/info.txt'.format(overwrite_backup_path), 'w') as f:
            f.write('Overwrite time: {}\n'.format(format_time()))
            f.write('Confirmed by: {}'.format(info.player if info.is_player else '$Console$'))

        slot_folder = get_slot_folder(slot)
        server.logger.info('[AQB] Deleting world')
        remove_worlds(config['ServerPath'])
        server.logger.info('[AQB] Restore backup ' + slot_folder)
        copy_worlds(slot_folder, config['ServerPath'])

        server.start()
    finally:
        restoring_backup.release()


def trigger_abort(server, info):
    global abort_restore, slot_selected
    abort_restore = True
    slot_selected = None
    print_message(server, info, '终止操作！')


def list_backup(server, info, size_display=config['SizeDisplay']):
    def get_dir_size(dir):
        size = 0
        for root, dirs, files in os.walk(dir):
            size += sum([os.path.getsize(os.path.join(root, name)) for name in files])
        if size < 2 ** 30:
            return f'{round(size / 2 ** 20, 2)} MB'
        else:
            return f'{round(size / 2 ** 30, 2)} GB'

    print_message(server, info, '§d【槽位信息】§r', prefix='')
    for i in range(config['SlotCount']):
        j = i + 1
        print_message(
            server, info,
            RTextList(
                f'[槽位§6{j}§r] ',
                RText('[▷] ', color=RColor.green).h(f'点击回档至槽位§6{j}§r').c(RAction.run_command, f'{config["Prefix"]} back {j}'),
                format_slot_info(slot_number=j)
            ),
            prefix=''
        )
    if size_display:
        print_message(server, info, '备份总占用空间: §a{}§r'.format(get_dir_size(config['BackupPath'])), prefix='')


def print_help_message(server, info):
    if info.is_player:
        server.reply(info, '')
    for line in HelpMessage.splitlines():
        prefix = re.search(r'(?<=§7){}[\w ]*(?=§)'.format(config['Prefix']), line)
        if prefix is not None:
            print_message(server, info, RText(line).set_click_event(RAction.suggest_command, prefix.group()), prefix='')
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


def enable(server, info):
    if(config['Enable']):
        print_message(server, info, '§a插件功能§r已经是打开的')
        return
    try:
        config['Enable'] = True
        write()
    except:
        print_message(server, info, '§a修改§r保存失败')
        return
    print_message(server, info, '§a修改§r成功')
    schedule_backup(server, info)

def disable(server, info):
    if not config['Enable']:
        print_message(server, info, '§a插件功能§r已经是关闭的')
        return
    try:
        config['Enable'] = False
        write()
    except:
        print_message(server, info, '§a修改§r保存失败')
        return
    print_message(server, info, '§a修改§r成功')

def interval(server, info, time):
    t = int(time)
    if(t < 0 or t > 365 * 24 * 60):
        print_message(server, info, '输入不合法，允许的区间是§a({}, {})'.format(0, 365 * 24 * 60))
        return
    try:
        config['Interval'] = t
        write()
    except:
        print_message(server, info, '§a修改§r保存失败')
        return
    print_message(server, info, '§a修改§r成功，将在下次自动存档后生效')

def slot(server, info, slot):
    slot_count = int(slot)
    if(slot_count < 0 or slot_count > 100000):
        print_message(server, info, '输入不合法，允许的区间是§a(0, 100000)')
        return
    try:
        config['SlotCount'] = slot_count
        write()
    except:
        print_message(server, info, '§a修改§r保存失败')
        return
    print_message(server, info, '§a修改§r成功')

def on_info(server, info):
    if not info.is_user:
        if info.content == 'Saved the game':
            global game_saved
            game_saved = True
        return

def on_user_info(server, info):
    command = info.content.split()
    if len(command) == 0 or command[0] != config['Prefix']:
        return

    cmd_len = len(command)

    # MCDR permission check
    if cmd_len >= 2 and command[1] in config['MinimumPermissionLevel'].keys():
        if server.get_permission_level(info) < config['MinimumPermissionLevel'][command[0]]:
            print_message(server, info, '§c权限不足！§r')
            return

    # !!aqb
    if cmd_len == 1:
        print_help_message(server, info)
    
    # !!aqb help
    elif cmd_len == 2 and command[1] == 'help':
        print_help_message(server, info)

    # !!aqb enable
    elif cmd_len == 2 and command[1] == 'enable':
        enable(server, info)
    
    # !!aqb disable
    elif cmd_len == 2 and command[1] == 'disable':
        disable(server, info)

    # !!aqb interval <minutes>
    elif cmd_len == 3 and command[1] == 'interval':
        interval(server, info, command[2])

    # !!aqb slot <number>
    elif cmd_len == 3 and command[1] == 'slot':
        slot(server, info, command[2])

    # !!aqb back [<slot>]
    elif cmd_len in [2, 3] and command[1] == 'back':
        restore_backup(server, info, command[2] if cmd_len == 3 else '1')

    # !!aqb confirm
    elif cmd_len == 2 and command[1] == 'confirm':
        confirm_restore(server, info)

    # !!aqb abort
    elif cmd_len == 2 and command[1] == 'abort':
        trigger_abort(server, info)

    # !!aqb list
    elif cmd_len == 2 and command[1] == 'list':
        list_backup(server, info)

    else:
        print_message(server, info, command_run(
            '参数错误！请输入§7{}§r以获取插件信息'.format(config['Prefix']),
            '点击查看帮助',
            config['Prefix']
        ))


class AutoSave(Thread):
        def __init__(self, server):
                Thread.__init__(self)
                self.shutdown_flag = False
                self.server = server

        def run(self):
                while(not self.shutdown_flag):
                        time.sleep(60 * config['Interval'])
                        if self.shutdown_flag:
                                return
                        if(config['Enable']):
                                class Info():
                                        def __init__(self):
                                            self.isPlayer = False
                                            self.is_player = False
                                            self.player = '@a'
                                info = Info()
                                schedule_backup(self.server, info)

        def shutdown(self):
                self.shutdown_flag = True

def on_load(server, old):
    server.add_help_message(config['Prefix'], command_run('全自动§a备份§r/§c回档§r，§6{}§r槽位'.format(config['SlotCount']), '点击查看帮助信息', config['Prefix']))
    global creating_backup, restoring_backup, autosave
    if hasattr(old, 'creating_backup') and type(old.creating_backup) == type(creating_backup):
        creating_backup = old.creating_backup
    if hasattr(old, 'restoring_backup') and type(old.restoring_backup) == type(restoring_backup):
        restoring_backup = old.restoring_backup
    autosave = AutoSave(server)
    autosave.start()
    read(server)


def on_unload(server):
    global abort_restore, plugin_unloaded
    abort_restore = True
    plugin_unloaded = True
    autosave.shutdown()
