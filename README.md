# AutoQuickBackup
---------

一个支持多槽位的自动快速备份＆回档插件，由[QuickBackupM](https://github.com/TISUnion/QuickBackupM)改编而来

为保证时间效率，仅支持全量备份，且不会压缩

需要 `0.8.2-alpha` 以上的 [MCDReforged](https://github.com/Fallen-Breath/MCDReforged)

![snapshot](https://raw.githubusercontent.com/XiaoHuiHui233/AutoQuickBackup/master/snapshot.png)

备份的存档将会存放至 auto_qb_multi 文件夹中，文件目录格式如下：
```
mcd_root/
    MCDReforged.py

    config/
        AutoQuickBackup/
            config.yml
    
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
```

## 命令格式说明

`!!aqb` 显示帮助信息

`!!aqb help` 显示帮助信息

`!!aqb enable` 启用自动备份，会强制进行一次备份

`!!aqb disable` 关闭自动备份

`!!aqb interval <minutes>` 设置自动备份的间隔时间为 `<minutes>` 分钟

`!!aqb slot <number>` 调整槽位个数为 `<number>` 个

注意，若输入 `<number>` 小于当前槽位，不会导致真实槽位数的减小

减少的槽位仍在硬盘中存在，只是不会存在于列表中，也不会被新存档覆盖

`!!aqb back [<slot>]` 回档为槽位 `<slot>` 的存档

当 `<slot>` 未被指定时默认选择槽位 `1`

`!!aqb confirm` 在执行 `back` 后使用，再次确认是否进行回档

`!!aqb abort` 在任何时候键入此指令可中断回档

`!!aqb list` 显示各槽位的存档信息

在 MCDR 环境下，默认配置下 `!!aqb back` 、 `!!aqb enable` 、 `!!aqb disable` 、 `!!aqb slot` 以及 `!!aqb interval` 需要权限等级 `helper`

## 配置项说明

不同于QuickBackupM，AutoQuickBackup会在MCDReforged的config文件夹下生成配置文件

可以通过修改配置文件中的信息来配置 AutoQuickBackup 插件，配置文件遵循yaml语法

### Enable

默认值: `Enable: True`

是否开启自动存档的功能

注意，使用 `!!aqb disable` 关闭自动存档功能会将该配置项设为 `False`

这表示，即使在服务器重启后，仍需通过命令 `!!aqb enable` 或者修改本配置项为 `True`

来开启本插件自动存档的功能

### Interval

默认值: `Interval: 5`

相邻两次备份间隔时间（单位：分钟）

不支持浮点数

### SizeDisplay

默认值: `SizeDisplay: True`

查看备份列表是否显示占用空间

### SlotCount

默认值: `SlotCount: 5`

存档槽位的数量

### Prefix

默认值: `Prefix: '!!aqb'`

触发指令的前缀

### BackupPath

默认值: `BackupPath: './auto_qb_multi'`

备份储存的路径

### TurnOffAutoSave

默认值: `TurnOffAutoSave: True`

是否在备份时临时关闭自动保存（这里的自动保存是指服务端定时对世界的保存，并非插件备份功能）

### IgnoreSessionLock

默认值: `IgnoreSessionLock: True`

是否在备份时忽略文件 `session.lock`。这可以解决 `session.lock` 被服务端占用导致备份失败的问题

### WorldNames

默认值:

```
WorldNames:
  - 'world'
```

需要备份的世界文件夹列表，原版服务端只会有一个世界，在默认值基础上填上世界文件夹的名字即可

对于非原版服务端如水桶、水龙头服务端，会有三个世界文件夹，此时可填写：
```
WorldNames:
  - 'world'
  - 'world_nether'
  - 'world_the_end'
```

### MinimumPermissionLevel

默认值:

```
MinimumPermissionLevel:
  help: 1
  enable: 2
  disable: 2
  interval: 2
  slot: 2
  back: 2
  confirm: 1
  abort: 1
  list: 0
```

一个字典，代表使用不同类型指令需要权限等级。数值含义见[此处](https://github.com/Fallen-Breath/MCDReforged/blob/master/doc/readme_cn.md#权限)

注意，此处将字典以yaml的形式进行保存

把所有数值设置成 `0` 以让所有人均可操作
