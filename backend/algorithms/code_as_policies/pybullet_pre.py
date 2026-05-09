import pybullet as p
import pybullet_data

# Connect to the physics engine
p.connect(p.GUI)

# Set simulation parameters
p.setGravity(0, 0, -9.8)
p.setTimeStep(1 / 240.0)
p.setPhysicsEngineParameter(
    fixedTimeStep=1/500,  # smaller timestep for better stability
    numSolverIterations=50
)
p.resetDebugVisualizerCamera(cameraDistance=1.5, cameraYaw=0, cameraPitch=-40, cameraTargetPosition=[0, 0, 0])

# Load ground plane
p.setAdditionalSearchPath(pybullet_data.getDataPath())
p.loadURDF("plane.urdf")

# Load robot arm
robot_id = p.loadURDF(
    "ur5e/ur5e.urdf",
    basePosition=[0, 0, 0],
    useFixedBase=True
)
num_joints = p.getNumJoints(robot_id)

# Lock base joints
for joint_index in range(num_joints):
    joint_info = p.getJointInfo(robot_id, joint_index)
    if joint_info[2] == p.JOINT_FIXED:
        p.setJointMotorControl2(robot_id, joint_index, p.POSITION_CONTROL, targetPosition=0)

# Set initial pose and PD control
initial_joint_positions = [0, -1.57, 1.57, -1.57, -1.57, 0]
for i, pos in enumerate(initial_joint_positions):
    p.resetJointState(robot_id, i, pos)
    p.setJointMotorControl2(
        robot_id, i, p.POSITION_CONTROL,
        targetPosition=pos, force=500,
        positionGain=0.03, velocityGain=1
    )

# Adjust camera
p.resetDebugVisualizerCamera(cameraDistance=1.0, cameraYaw=90, cameraPitch=-30, cameraTargetPosition=[0.5, 0, 0.5])

# Real-time simulation loop
while True:
    p.stepSimulation()
