# 安装准备
```shell
pip3 install flight_profiler
```

该命令会将flight_profiler安装到当前Python3的site-packages目录下。安装完成后，您可以使用全局命令`flight_profiler`进行调试。

# 启动调试
首先找到目标调试进程，通过ps命令查看进程PID：

```shell
ps -ef | grep python
```

启动调试，参数传入目标PID：

```shell
flight_profiler pid
```

随后可以开始输入调试命令。

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/attach_success.png)

# 命令指南
## 命令描述help
查看可使用的所有命令以及命令的具体使用方式。

```shell
help [command]
```

### 参数解析
| 参数 | 必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| command | 否 | 需查看的命令名称 | stack |

### 输出展示
![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/help.png)

## 线程栈分析stack
### 线程栈stack
#### Linux 环境
查看进程当前运行的所有线程的Python执行栈信息，并支持分析native栈以及导出到文件。

```shell
stack [pid] [-f <value>] [--native]
```

##### 参数解析
| 参数 | 必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| pid | 否 | 分析的进程ID，默认为被注入进程的ID | 3303 |
| -f, --filepath | 否 | 线程栈导出到的文件位置 | /home/admin/stack.log |
| --native | 否 | 是否分析Python线程的本地栈，默认为False | --native |

##### 输出展示
命令示例：

```shell
# 查看Python线程栈
stack

# 查看Python线程的native栈
stack --native

# 导出执行栈信息到文件中
stack -f ./stack.log
```

执行`stack`命令可在控制台展示所有线程的栈信息。

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/stack_linux.png)
分析native线程栈：

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/stack_linux_native.png)


#### Mac环境
查看进程当前运行的所有线程的Python执行栈信息，并支持导出到文件。

```shell
stack [filepath]
```

##### 参数解析
| 参数 | 必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| filepath | 否 | 线程栈导出到的文件位置 | /home/admin/stack.log |

##### 输出展示
执行`stack`命令可在控制台展示所有线程的栈信息。

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/stack_mac.png)


## 方法执行观测watch
### 观察执行方法输入、输出及耗时
watch命令如下：

```shell
watch module [class] method [--expr <value>] [-e] [-r] [-v] [-n <value>] [-x <value>] [-f <value>]
```

#### 参数解析
| 参数                  | 必填 | 含义                                                                                                                                                                                                   | 示例                            |
|---------------------|----|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------|
| module              | 是  | 方法所在的模块                                                                                                                                                                                              | __main__、my.pkg.modulename    |
| class               | 否  | 方法所在的类名                                                                                                                                                                                              | className                     |
| method              | 是  | 观测的方法名                                                                                                                                                                                               | methodName                    |
| -nm --nested-method | 否  | 是否观测深度为1的嵌套方法                                                                                                                                                                                        | -nm nested_method             |
| --expr              | 否  | 观测的表达式。<br/>书写格式参考Python方法入参为(target, return_obj, cost, *args, **kwargs)，其中target为类实例（如果调用属于类方法），return_obj为方法返回对象，cost为方法调用耗时，*args为调用的非指定入参，**kwargs为调用的指定入参，需要返回关于上述参数的右值表达式。<br/>默认为args, kwargs | --expr args,kwargs,return_obj |
| -e                  | 否  | exception，只在方法执行发生异常时记录                                                                                                                                                                              | -e                            |
| -r, --raw           | 否  | 是否直接展示目标的字符串表达                                                                                                                                                                                       | -r                            |
| -v, --verbose       | 否  | 是否展示目标列表/字典的所有子项                                                                                                                                                                                     | -v                            |
| -x, --expand        | 否  | expand，展示被观察对象的深度，默认为1，最大为4                                                                                                                                                                          | -x 2                          |
| -f, --filter        | 否  | 过滤参数表达式，只有通过过滤条件的调用才会进行观测。<br/>书写格式与--expr指令相同，需要返回bool表达式。                                                                                                                                          | -f args[0]["query"]=='hello'  |
| -n, --limits        | 否  | 被观测的最大展示条数，默认为10                                                                                                                                                                                     | -n 50                         |

**<font style="color:#DF2A3F;">表达式说明：</font>**

1. 若表达式值带空格，则需要用引号进行包括，例如-f "args[0] == 'hello'"
2. 若观测值中含有类实例，针对类实例中的私有变量（即__开头的字段），用户需要显式修改访问方式，例如args[0]为类A的实例，类A包含__val变量，则表达式应为： --expr args[0]._A__val 即在私有变量前添加 "_类名" 前缀（Python 规约）

#### 输出展示
命令示例：

```shell
# watch 模块函数
watch __main__ func -x 2

# watch 模块函数，并过滤参数
watch __main__ func -f "args[0][\"query\"]=='hello'"

# watch 模块函数，并过滤返回值
watch __main__ func -f "return_obj['success']==True"

# watch 模块函数，并过滤函数调用耗时
watch __main__ func --expr "{return_obj,args}" -f "cost>10"

# watch 类函数
watch __main__ classA func
```

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/watch.png)

输出的字段信息包括：

+ cost：方法执行的耗时，单位毫秒
+ result：针对watch命令表达式的逐项观测结果
    - EXPR：表达式名称，如arg代表位置参数，kwargs代表关键字参数
    - VALUE：表达式值，如arg表达式展示为参数列表，kwargs表达式展示为key-value值

## 方法内部调用路径观测trace
### 观察方法的执行路径及耗时
trace命令如下：

```shell
trace module [class] method [-i <value>] [-nm <value>] [-et <value>] [-d <value>] [-n <value>] [-f <value>]
```

#### 参数解析
| 参数                   | 是否必填 | 含义                                                                                                                                                 | 示例                               |
|----------------------| --- |----------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------|
| module               | 是 | 方法所在的模块                                                                                                                                            | __main__、my.pkg.modulename       |
| class                | 否 | 方法所在的类名                                                                                                                                            | className                        |
| method               | 是 | 观测的方法名                                                                                                                                             | methodName                       |
| -nm --nested-method  | 否  | 是否观测深度为1的嵌套方法                                                                                                                                      | -nm nested_method                |
| -d, --depth          | 否 | 只展示深度为depth的方法调用, 当指定depth参数时interval采样间隔被限制为0                                                                                                     | -d 3                             |
| -i, --interval       | 否 | 只观测执行耗时大于#{interval}的内部方法调用，默认为0.1ms，注意#{interval}越小，对方法执行的观测开销越大，经测试简单文本推理方法在默认情况的开销在10%～20%左右，随被观测方法复杂情况波动。                                      | -i 1                             |
| -et, --entrance_time | 否 | 只展示执行时间超过#{entrance_time}的方法调用                                                                                                                     | -et 30                           |
| -f, --filter         | 否 | 过滤参数表达式，只有通过过滤条件的调用才会进行观测。<br/>书写格式参考Python方法入参为(target, *args, **kwargs)，需要返回关于target, args和kwargs的bool表达式，target为类实例（如果调用属于类方法），args与kwargs为被调用方法的入参 | -f "args[0][\"query\"]=='hello'" |
| -n, --limits         | 否 | 被观测的最大展示条数，默认为10                                                                                                                                   | -n 50                            |

#### 输出展示
命令示例：

```shell
# 追踪模块函数
trace __main__ func

# 追踪模块函数，并只追踪函数执行耗时超过1ms的函数调用
trace __main__ func -i 1

# 追踪类函数
trace __main__ classA func
```

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/trace.png)

## 跨时间方法调用观测tt
### 跨时间区段下对方法调用进行观测
tt命令如下：

```shell
tt [-t module [class] method] [-n <value>] [-l] [-i <value>] [-d <value>] [-da] [-x <value>] [-p] [-f <value>] [-r] [-v] [-m <value>]
```

#### 参数解析：
| 参数 | 是否必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| -t module [class] method | 否 | 对指定模块下的方法调用进行时空观测，module/class/method定义与watch/trace中相同 | -t moduleA classA func |
| -nm --nested-method | 否  | 是否观测深度为1的嵌套方法                                                                                                                                                                                        | -nm nested_method             |
| -n, --limits <value> | 否 | 被观测的最大展示条数，默认为50 | -n 50 |
| -l, --list | 否 | 展示所有方法调用区段 | -l |
| -i, --index <value> | 否 | 展示索引所对应的方法调用详情 | -i 1000 |
| -d, --delete <value> | 否 | 删除索引对应的调用记录 | -d 1000 |
| -da, --delete_all | 否 | 删除所有的调用记录 | -da |
| -r, --raw | 否 | 是否直接展示目标的字符串表达，即repr(target) | -r |
| -v, --verbose | 否 | 是否展示目标列表/字典的所有子项 | -v |
| -x, --expand | 否 | expand，展示被观察对象的深度，默认为1，最大为4 | -x 2 |
| -p, --play | 否 | 是否要重新触发历史调用，与-i同用，使用索引指定的调用参数 | -i 1000 -p |
| -f, --filter | 否 | 过滤参数表达式，参考watch命令 | -f "args[0][\"query\"]=='hello'" |
| -m, --method | 否 | 过滤方法名，格式为module.class.method，如果方法为类方法，则class填None，与-l通用 | -l -m moduleA.classA.methodA |

#### 输出展示
命令示例：

```shell
# 记录模块方法
tt -t __main__ func

# 记录类方法
tt -t __main__ A func

# 展示被调用方法记录列表
tt -l

# 展示指定调用详情
tt -i 1000 -x 3

# 重新触发索引为1000的调用，使用相同的输入
tt -i 1000 -p

# 只观测返回值为'success'，耗时大于10ms的记录
tt -t __main__ func -f "return_obj['success']==True and cost>10"

# 只观测第一个方法参数包含query字段且为"hello"的请求
tt -t __main__ func -f "args[0][\"query\"]=='hello'"
```

观测方法调用：

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/timetunnel_1.png)

指定索引：

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/timetunnel_2.png)

重新执行历史调用：

可以看到索引已经发生变化：1000 -> 1010

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/timetunnel_3.png)

## 全局变量查看getglobal
### 观察模块全局变量/类的静态变量
getglobal命令如下：

```shell
getglobal module [class] field [-x <value>] [-e <value>] [-r] [-v]
```

#### 参数解析
| 参数 | 是否必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| module | 是 | 字段所在的模块 | __main__、my.pkg.modulename |
| class | 否 | 字段所在的类名 | className |
| field | 是 | 字段的名称 | fieldName |
| -e, --expr | 否 | 观测对象的表达式，格式参考Python方法入参为(target)，target为被观察对象，需要返回关于target的右值表达式。 | -e target.fieldA |
| -x, --expand | 否 | expand，展示被观察对象的深度，默认为1，最大为4 | -x 2 |
| -r, --raw | 否 | 是否直接展示目标的字符串表达 | -r |
| -v, --verbose | 否 | 是否展示目标列表/字典的所有子项 | -v |

#### 输出展示
由__main__启动的python文件的对应变量，使用如下命令：

```shell
# 模块变量
getglobal __main__ g_list

# 类静态变量
getglobal __main__ classA static_field
```

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/getglobal.png)

## PythonVm 工具vmtool
### 查看类实例getInstances
命令如下：

```shell
vmtool -a getInstances -c module class [-e <value>] [-x <value>] [-n <value>] [-v] [-r]
```

#### 参数解析
| 参数 | 是否必填 | 含义 | 示例 |
|-----------------------| --- | --- | --- |
| module | 是 | 类所在的模块 | __main__、my.pkg.modulename |
| class | 是 | 类名 | className |
| -e, --expr <value> | 否 | 观测对象的表达式，格式参考Python方法入参为(instances)，instances为对应类的实例列表，需要返回关于instances的右值表达式。 | -e instances[0].fieldA |
| -x, --expand <value> | 否 | expand，展示被观察对象的深度，默认为1，最大为4 | -x 2 |
| -r, --raw | 否 | 是否直接展示目标的字符串表达 | -r |
| -v, --verbose | 否 | 是否展示目标列表/字典的所有子项 | -v |
| -n, --limits <value> | 否 | 控制展示的实例数量，默认10，-1代表不限制 | -n 1|

#### 输出展示
由__main__启动的python文件的对应变量，使用如下命令：

```shell
# 查看类A的所有实例
vmtool -a getInstances -c __main__ A

# 查看类A的实例的变量
vmtool -a getInstances -c __main__ A -e instances[0].val
```

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/vmtool.png)

### 强制垃圾回收forceGc
命令如下：

```shell
vmtool -a forceGc
```

#### 输出展示
```shell
vmtool -a forceGc
```

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/vmtool_gc.png)

## 获取文件模块名称module
该命令会输出文件名在注入进程中对应的模块，方便用户根据异常栈直接定位方法或变量。

module命令如下：

```shell
module filepath
```

### 参数解析
| 参数 | 必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| filepath | 是 | 需要转义的文件名 | /home/admin/main.py |

### 输出展示
命令示例：

```shell
# 对应模块为__main__.py
module ~/tt_main.py

# 未导入到指定进程中
module ~/not_exist.py
```

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/module_exist.png)

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/module_not_exist.png)

## 程序热点火焰图Perf
对程序进程采样profile，生成火焰图，方便用户优化程序热点，基于[py-spy](https://github.com/benfred/py-spy)实现。

perf命令：

```shell
perf [pid] [-f <value>] [-r <value>] [-d <value>]
```

### 参数解析
| 参数 | 必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| [pid] | 否 | 分析的进程ID，默认是被注入进程 | 123/不填 |
| -f, --filepath <value> | 否 | 火焰图导出的路径，默认导出到当前目录下的flamegraph.svg | -f ~/sample.svg |
| -r --rate <value> | 否 | 每秒采样数，默认是100 | -r 1000 |
| -d --duration <value> | 否 | 持续时间，单位为秒，默认是等待用户打断 | -d 30 |

### 输出展示
命令示例：

```shell
perf

# 将输出导出到～/flamegraph.svg下
perf -f ~/flamegraph.svg

# 采样30s
perf -d 30 -f ~/flamegraph.svg
```

<font style="color:#DF2A3F;">在MacOS下使用该命令，py-spy需要用户的root权限</font>

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/perf.png)

## 开启交互式console
在指定进程中开启交互式console，支持用户执行自定义脚本，获取系统属性等操作。

console命令：

```shell
console
```

### 输出展示
命令示例：

```shell
console
```

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/console.png)


## 内存分析mem
### 内存Summary
`summary`命令可以按变量类型统计内存占用量：

```shell
mem summary
```

```shell
mem summary --limit 100 --order descending
```

其中`limit`参数控制TOP展示数量，`order`控制按大小递减或递增（descending/ascending）。

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/mem_summary.png)

### 内存diff
该命令可以比较两个时间点的内存大小差异：

```shell
mem diff --interval 10 --limit 100 --order descending
```

如上述命令，取10s前后的内存快照，比对差异，按大小递减展示差异最大的内存变量类型，效果如下：

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/mem_diff.png)

## GIL锁性能分析
### GIL锁损耗统计
```shell
gilstat on
```

执行`gilstat on`命令后，控制台会每隔5s输出每个线程的GIL锁损耗统计。

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/gilstat_on.png)

输出信息的字段包括：

+ thread_name：线程名称
+ takecnt：累积获取GIL锁次数
+ hold_all：累积持有GIL锁时间，单位是纳秒，1ms = 1000000ns
+ holdavg：平均每次从成功获取GIL锁后持有GIL锁时间，持有GIL锁时，其他线程会暂停运行，会导致P99升高。<font style="color:#DF2A3F;">性能优化小Tip：该值可以反馈该线程是否计算过重，可以考虑降低连续CPU计算时间，适当让出时间片给其他线程</font>。
+ take_all：获取GIL锁时累积等待时间，因为只有一个线程能获得GIL锁，其他线程take GIL lock时需要等待。可以理解为线程阻塞获取互斥锁的时间。
+ takeavg：平均获取GIL锁等待时间
+ drogcnt：累积释放GIL锁次数，一般等于takecnt
+ drog_all：累积释放GIL锁消耗的时间，一般很小
+ dropavg：平均释放GIL锁等待时间

### GIL长尾损耗监控
```shell
gilstat on 5 5
```

第一个参数5代表获取GIL锁耗时阈值5ms，持有GIL锁耗时阈值5ms。即当有线程获取GIL锁阻塞超过5ms，或者线程GIL锁持有时间超过5ms，则会打印一条监控。该命令可以分析线上一些长尾超时query。

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/gilstat_report.png)

## PyTorch框架采样
### 对函数执行进行采样profile
基于Torch Profiler实现，能够采样torch框架中的执行函数的耗时，以及在CPU或GPU上执行。

命令示例：

```shell
torch profile module [class] method [-f <value>]
```

#### 参数解析
| 参数 | 是否必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| module | 是 | 方法所在的模块 | __main__、my.pkg.modulename |
| class | 否 | 方法所在的类名 | className |
| method | 是 | 观测的方法名 | methodName |
| -nm --nested-method | 否  | 是否观测深度为1的嵌套方法                                                                                                                                                                                        | -nm nested_method             |
| -f --filepath <value> | 否 | 采样文件的导出到的文件路径，默认到当前目录下的trace.json | -f ~/trace.json |

#### 输出展示
命令示例：

```shell
# 采样__main__模块的A类的hello方法
torch profile __main__ A hello
```

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/torch_profile_1.png)

生成的trace.json文件需要放入chrome浏览器的<font style="color:#DF2A3F;">chrome://tracing/</font><font style="color:rgb(0, 0, 0);">路径下进行可视化，展示结果如图所示</font>

![](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/torch_profile_2.png)

### torch显存快照
基于Torch Profiler实现，能够对进程中的显存进行快照，或录制方法执行过程中的显存分配行为：

```shell
torch memory [-s] [-r module [class] method] [-f <value>]
```

#### 参数解析
| 参数 | 是否必填 | 含义 | 示例 |
| --- | --- | --- | --- |
| -s, --snapshot | 否 | 是否对当前进程使用的显存空间进行快照 | -s |
| -r, --record | 否（-s, -r 选一） | 是否对方法执行过程中的torch框架显存分配动作进行录制，module、class、method与profile中保持一致 | -r module class |
| -nm --nested-method | 否  | 是否观测深度为1的嵌套方法                                                                                                                                                                                        | -nm nested_method             |
| -f --filepath <value> | 否 | 采样文件的导出到的文件路径，默认到当前目录下的snapshot.pickle | -f ~/snapshot.pickle |

#### 输出展示
命令示例：

```shell
# 对当前进程使用的torch显存进行快照
# 由于torch监测显存的
torch memory -s

# 对方法执行过程中的显存分配动作进行观测
torch memory -r __main__ Solution call
```

生成的snapshot.pickle文件需要放入[https://pytorch.org/memory_viz](https://pytorch.org/memory_viz)中进行分析<font style="color:rgb(0, 0, 0);">，展示结果如图所示，其中左侧列表为分配和收集的时序行为：</font>

![img.png](https://raw.githubusercontent.com/alibaba/PyFlightProfiler/refs/heads/main/docs/images/torch_mem_profile1.png)

关于具体原理/如何从图中获取有效信息：[https://pytorch.org/docs/2.5/torch_cuda_memory.html](https://pytorch.org/docs/2.5/torch_cuda_memory.html)

<font style="color:#DF2A3F;">注意：</font>

由于torch框架下对历史显存分配的采样并未开启，因此对<font style="color:#DF2A3F;">已分配的显存是无法追溯堆栈信息</font>的，若要想看程序从启动开始的分配行为（一般都在<font style="color:#DF2A3F;">开发环境</font>），可以用如下方法：

1. 将主要内存分配延迟到一个方法中，再使用record录制方法执行
2. 在程序开始前加入一小段脚本，标识开启采样
    1. 针对2.0.0 <= torch < 2.1.0 版本，在程序起始加入，再使用snapshot命令查看
        ```python
        from torch.cuda.memory import _record_memory_history
        _record_memory_history (enabled=True, trace_alloc_max_entries=100_000, trace_alloc_record_context=True)
        ```

    2. 针对torch >= 2.1.0 版本，在程序起始加入
        ```python
        from torch.cuda.memory import _record_memory_history
        _record_memory_history()
        ```
