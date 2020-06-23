# ExAutoQuickBackup
---------

一个支持多槽位自动快速备份和回档的 MCDR 插件，能够灵活安排备份存留的时长，使得需回档时不同量级的时间之前的备份都有保留。具体的存留策略可配置，亦可根据需求写代码扩展。

此插件由由 [QuickBackupM](https://github.com/TISUnion/QuickBackupM) 改编而来的 [AutoQuickBackup](https://github.com/XiaoHuiHui233/AutoQuickBackup) 改编而来。相比于 AutoQuickBackup 和 / 或 QuickBackupM，ExAutoQuickBackup 除上述特点外，还
- 能够删除备份槽位。
- 在备份时中间有空槽位的情况下不会删除最后一个槽位。
- 尝试通过同一时间只允许进行一个操作提高安全性，如自动备份会等待删除存档完成等。

*同 QuickBackupM 和 AutoQuickBackup，仅支持全量备份，暂不支持压缩。*

## 依赖

- [MCDReforged](https://github.com/Fallen-Breath/MCDReforged)
  - `0.8.2-alpha` 以上。
- [Python](https://python.org)
  - `3.8`，但向后兼容 `3.6`。如果 `3.8` 之前的版本出现了兼容性问题，请提 [issue](https://github.com/TRCYX/AutoQuickBackup/issues/new)。

## 使用方法

ExAutoQuickBackup 使用方法和 QuickBackupM、AutoQuickBackup 类似。

### 命令格式说明

- 帮助
  - `!!eqb` 显示帮助信息
  - `!!eqb help` 显示帮助信息
- 回档与确认
  - `!!eqb back [<slot>]` 回档为槽位 `<slot>` 的存档
    - 当 `<slot>` 未被指定时默认选择槽位 `1`。
  - `!!eqb confirm` 在执行 `back` 后使用，再次确认是否进行回档
  - `!!eqb abort` 在任何时候键入此指令可中断回档
- 槽位操作
  - `!!eqb list` 显示各槽位的存档信息
  - `!!eqb del <slot>` 删除槽位 `<slot>`
- 部分配置
  - `!!eqb enable` 开启自动备份（不同于 `AutoQuickBackup`，不会立刻进行一次备份）
  - `!!eqb disable` 关闭自动备份
  - `!!eqb slot <number>` 调整槽位个数为 `<number>` 个
    - 若输入 `<number>` 小于当前槽位，不会导致真实槽位数减少。减少的槽位仍在硬盘中存在，只是不会存在于列表中，也不会被新存档覆盖。

*一些命令需要特定权限（可配置）。默认配置下 `!!eqb back` 、 `!!eqb enable` 、 `!!eqb disable`、`!!eqb slot` 和 `!!eqb del` 需要 MCDR 的权限等级 `helper`。*

### 目录结构

备份的存档将会存放至 `ex_auto_qb_multi` 文件夹中，文件目录格式如下：
```
mcd_root/
    MCDReforged.py

    config/
        ex_auto_quick_backup.yml
    
    server/
        world/
        
    ex_auto_qb_multi/
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

### 配置项说明

ExAutoQuickBackup 会在 MCDR 的 `config` 文件夹下生成 `YAML` 格式的配置文件 `ex_auto_quick_backup.yml`，可以通过修改此文件来配置插件。

*相比于 `AutoQuickBackup`，删去了 `Interval` 而增加了 `Strategy` 和 `StrategyConfig`。*

#### Strategy 和 StrategyConfig

`Strategy` 表示存留备份的策略名称。策略负责管理备份的去留，以及提供进行备份的周期。`StrategyConfig` 为其设置，对于不同的策略可能意义不同。

默认值：
```
Strategy: default
StrategyConfig:
- 10min
- 1h
- 3h
- 1d
- 2d
- 3d
- 5d
- 10d
- 1M
- 2M
```

所有策略的列表如下（目前只有默认策略 `default`）：

##### default

`StrategyConfig` 为一时长列表，此策略尝试对于每相邻两个时长，在距当前这两个时长所表示的时间段内保留一个存档。备份周期为列表中最小的时间。如在其为默认值
```
[10min, 1h, 3h, 1d, 2d, 3d, 5d, 10d, 1M, 2M]
```
的情况下，会每 10 分钟备份一次，并尝试在距当前 10 分钟内、10 分钟至 1 小时内、1 小时至 3 小时内等各保留一个备份。时长默认单位为分钟，也可以使用如下时间单位（不区分大小写）：

| 单位 | 含义 |
| ---- | ---- |
| min | 分钟 |
| h | 小时 |
| d | 天 |
| M | 月（30天） |
| Y | 年（365天） |

注意距当前不同时间段的存档的分配不是完全精准的，但大致会与设置相符合。如果每个时间段的长度是前一个时间段长度的倍数，那么 `default` 策略能够精准地让每个时间段内各有一个备份。

另外，如果槽位总数大于时长列表长度，`default` 策略会大致以最后一段时间的长度为周期存留更老的备份，如默认情况下此周期为 `2M - 1M = 1M`。如果槽位被填满，编号最大的（理应为最老的）槽位会被删除。

**通过代码增加其他策略的方法详见[后文](#增加其他策略)。**

#### WorldNames

需要备份的世界文件夹列表，原版服务端只会有一个世界，在默认值基础上填上世界文件夹的名字即可。

默认值：
```
WorldNames:
  - 'world'
```

对于水桶、水龙头等一些非原版服务端，会有三个世界文件夹，此时可填写：
```
WorldNames:
  - 'world'
  - 'world_nether'
  - 'world_the_end'
```

#### MinimumPermissionLevel

一个字典，代表不同指令所需要的权限等级。数值含义见[此处](https://github.com/Fallen-Breath/MCDReforged/blob/master/doc/readme_cn.md#权限)。

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

字典以 `YAML` 的形式进行保存。把所有数值设置成 `0` 以让所有人均可操作。

#### SlotCount

存档槽位的数量。

默认值：`10`

#### Enable

是否开启自动存档的功能。可以通过 `!!eqb enable / disable` 修改。

默认值：`True`

#### SizeDisplay

查看备份列表是否显示占用空间。

默认值：`True`

#### Prefix

指令的前缀。

默认值：`'!!eqb'`

#### BackupPath

备份储存的路径。

默认值：`'./auto_qb_multi'`

#### TurnOffAutoSave

是否在备份时临时关闭服务器的自动保存功能。

默认值：`True`

#### IgnoreSessionLock

是否在备份时忽略文件 `session.lock`。这可以解决 `session.lock` 被服务端占用导致备份失败的问题。

默认值：`True`

## 增加其他策略

ExAutoQuickBackup 的策略继承自 `Strategy` 类：
```Python
class Strategy:
    def interval(self) -> float:
      ...

    def decide_which_to_keep(self, ages: List[float]) -> List[bool]:
      ...
```

若要增加新的策略，可以继承此类。策略对象初始化需接受两个参数，依次为 MCDR 提供的 `server` （方便输出错误等）和 `StrategyConfig` 反序列化得到的对象。后者可以随需要为不同 `YAML` 能表示的类型。

`interval` 方法返回自动备份的周期，**以秒为单位**，如 `default` 策略返回 `StrategyConfig` 中的最小者。程序中 `time_length_to_seconds` 函数可以将以分钟为单位的时间或者带单位的字符串转化为以秒为单位。

`decide_which_to_keep` 方法接受一个 `float` 列表 `ages`，为所有现存备份已存在的时长，从小到大排列，以秒为单位。此方法需要返回一个等长的 `bool` 列表，按同于 `ages` 的顺序表示每个备份是否保留（`True` 为保留）。*如果返回值全为 `True` 且槽位已经填满，编号最大的槽位则会被强制删除。*

在实现了新的策略后，将其以 `<名称>: <类名 / 构造函数名>` 的形式加入程序中的 `STRATEGIES` 字典，即可在配置文件中以 `<名称>` 调用。

（返回一 `Strategy` 而接受这两个参数的函数也可以加入 `STRATEGIES` 而成为独立的策略。）

欢迎提交 [PR](https://github.com/MCDReforged-Plugins/PluginCatalogue/compare)！
