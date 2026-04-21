GB/T 18487.1—2023

附录B充电机 | 车辆插头 | GB 车辆适配器 | 车辆插座 | 中欧美电动汽车
---|---|---|---|---
PE | PE | | PE | 车身地
$U1, 12.0V$ | $S$ | $Rc', 1.0k\Omega$ | $R3', 100k\Omega$ | $R4', 2.74k\Omega$ | $R4c', 830\Omega$ | $R4, 1.3k\Omega$ | $U2, 12V$
$R1, 1.0k\Omega$ | $R2, 1.0k\Omega$ | $R3, 1.0k\Omega$ | | $S2'$ | $S2$ (2, 1, 0) | $Rv', 1.59k\Omega$ | $Rv, 1.0k\Omega$
检测点1 | $CC1$ | $CC1$ | $D1$ | 检测点2 | $Sv$ |
 | $CC2$ | $Rc'', 1.5k\Omega$ | $CC2$ | 检测点3 |

c) 连接至附录 B 充电机

**图 H.2 中欧美直流充电控制导引充电兼容解决方案（续）**

图 H.3 给出了采用车辆适配器与日本 CHAdeMO 2.x及以下充电机、欧美 CCS1 充电机、欧美 CCS2 充电机以及附录 B 充电机都兼容的电动汽车控制导引电路，即全球通用版本。

日本CHAdeMO 2.x及以下充电机 | 车辆插头 | CHAdeMO 车辆适配器 | 车辆插座 | 全球通用版本电动汽车
---|---|---|---|---
PE | PE | | PE | 车身地
$U1, 12.0V$ | $R1, 0.2k\Omega$ | $Rc', 200\Omega$ | $R3', 100k\Omega$ | $R4', 2.74k\Omega$ | $R4c', 830\Omega$ | $R4c, 1300\Omega$ | $R4, 1.3k\Omega$ | $U2, 12V$
$R2, 1.0k\Omega$ | $CP3$ | $CC1$ | $D1$ | $S2'$ | $S2$ (3, 2, 1, 0) | $Rv', 1.59k\Omega$ | $Rv, 1.0k\Omega$
检测点1 | $CS$ | $Rc'', 100\Omega$ | $CC2$ | 检测点2 | $Sv$ |
$d1$ | $d2$ | $Rd, 400\Omega$ | | 检测点3 |

a) 连接至 CHAdeMO2.x 以下充电机

欧美CCS1充电机 | 车辆插头 | CCS1车辆适配器 | 车辆插座 | 全球通用版本电动汽车
---|---|---|---|---
PE | PE | | PE | 车身地
$\pm12.0V, 1kHz$ | $S3$ | $R7, 330\Omega$ | $Rc', 2.1k\Omega$ | $R3', 100k\Omega$ | $R4', 2.74k\Omega$ | $R4c', 830\Omega$ | $R4c, 1300\Omega$ | $R4, 1.3k\Omega$ | $U2, 12V$
$R1, 1.0k\Omega$ | $R6, 150\Omega$ | | $S2'$ | $S2$ (3, 2, 1, 0) | $Rv', 1.59k\Omega$ | $Rv, 1.0k\Omega$
检测点1 | $CP$ | $CC1$ | $D1$ | 检测点2 | $Sv$ |
检测点PP | $PP$ | $Rc'', 360\Omega$ | $CC2$ | 检测点3 |

b) 连接至 CCS1 充电机

欧美CCS2充电机 | 车辆插头 | CCS2车辆适配器 | 车辆插座 | 全球通用版本电动汽车
---|---|---|---|---
PE | PE | | PE | 车身地
$\pm12.0V, 1kHz$ | $Re, 1.5k\Omega$ | $Rc', 300\Omega$ | $R3', 100k\Omega$ | $R4', 2.74k\Omega$ | $R4c', 830\Omega$ | $R4c, 1300\Omega$ | $R4, 1.3k\Omega$ | $U2, 12V$
$R1, 1.0k\Omega$ | | | $S2'$ | $S2$ (3, 2, 1, 0) | $Rv', 1.59k\Omega$ | $Rv, 1.0k\Omega$
检测点1 | $CP$ | $CC1$ | $D1$ | 检测点2 | $Sv$ |
 | $PP$ | $Rc'', 2500\Omega$ | $CC2$ | 检测点3 |

c) 连接至 CCS2 充电机

**图 H.3 全球通用直流充电控制导引充电兼容解决方案**

132