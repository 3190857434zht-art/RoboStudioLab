import pybullet as p
import pybullet_data
import time

# 连接物理引擎
p.connect(p.GUI)

# 设置仿真参数
p.setPhysicsEngineParameter(
    fixedTimeStep=1/500,  # 更小的时间步长
    numSolverIterations=200,
    useSplitImpulse=1,
    splitImpulsePenetrationThreshold=0.01
)
p.setAdditionalSearchPath(pybullet_data.getDataPath())
p.setGravity(0, 0, -9.8)

# 加载地面
floor = p.loadURDF("plane.urdf", [0, 0, 0], [0, 0, 0, 1])

# 加载机械臂
panda = p.loadURDF(
    "franka_panda/panda.urdf",
    [0, 0, 0.5],
    p.getQuaternionFromEuler([0, 0, 0])
)

# 锁定基座关节
p.createConstraint(
    panda, -1, -1, -1,
    p.JOINT_FIXED,
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0.5]
)

# 设置初始姿态和PD控制
initial_positions = [0, -0.785, 0, -2.356, 0, 1.571, 0.785]
for i in range(p.getNumJoints(panda)):
    if i < 7:
        p.resetJointState(panda, i, initial_positions[i])
    p.setJointMotorControl2(
        panda, i, p.POSITION_CONTROL,
        targetPosition=initial_positions[i] if i < 7 else 0,
        force=87,
        positionGain=0.5,
        velocityGain=1.0
    )

# 调整相机
p.resetDebugVisualizerCamera(3, 0, -50, [0, 0, 0.2])

# 实时仿真循环
p.setRealTimeSimulation(1)
try:
    while True:
        time.sleep(1/500)
except KeyboardInterrupt:
    p.disconnect()