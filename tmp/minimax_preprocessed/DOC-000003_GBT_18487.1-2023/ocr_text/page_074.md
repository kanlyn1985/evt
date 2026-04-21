GB/T 18487.1—2023

表 A.7 交流充电控制时序表（续）

| 时序 | 时序图例 | 状态 | 条件 | 时间 |
| :--- | :--- | :--- | :--- | :--- |
| 10.2<br>电动汽车不能对供电设备的终止充电状态做出响应 | 12V<br>9V<br>6V<br>检测点1 0V<br><br><br>-12V<br>AC电压 ON OFF<br>S2开关 closed open<br>AC电流 ON OFF<br>T13 T16<br>触发条件：状态 3' $\rightarrow$ 状态 3 | | 该时序出现在时序 9.1 之后，但是电动汽车不能做出响应，且不能将停止充电 | |
| | | 状态 3 | (16) 供电设备可带载断开交流供电回路 | (T16-T13) $\geqslant$ 6 s |
| 11<br>电动汽车唤醒供电设备数字通信模式 | 12V<br>9V<br>6V<br>检测点1 0V<br><br><br>-12V<br>AC电压 ON OFF<br>S2开关 closed open<br>AC电流 ON OFF<br>T17 T18 | 状态 2(2') $\rightarrow$ 状态 3(3') $\rightarrow$ 状态 2(2') | (17,18) 该时序为可选时序，用于数字通信。电动汽车控制 S2 的关断可用于唤醒供电设备数字通信模式。<br>该时序期间电动汽车不应充电 | 200 ms $\leqslant$ (T18-T17) $\leqslant$ 3 s |
| 12<br>其他任何状态进入异常状态 | 异常/故障<br>12V<br>9V<br>6V<br>检测点1 0V<br><br><br>-12V<br>AC电压 ON OFF<br>S2开关 closed open<br>AC电流 ON OFF<br>T26 T27<br>触发条件：任意状态 $\rightarrow$ 状态 0 | 状态 xx $\rightarrow$ 状态 0 | 其他任何状态进入异常状态，供电设备应断开交流供电回路。<br>电动汽车打开 S2(如有)。<br>连接方式 A 或 B 时，供电设备可在交流供电回路切断 100 ms 后可以解锁(如有) | 最大 100 ms<br><br><br>最大 3 s |

67