from lerobot.robots.so101_follower import SO101Follower
from lerobot.robots.so101_follower.config_so101_follower import SO101FollowerConfig

config = SO101FollowerConfig(port="/dev/ttyCH343USB0", id="scooping_follower", use_degrees=True)

robot = SO101Follower(config)
robot.connect()
state = robot.get_observation()
print("关节状态:", state)
robot.disconnect()
