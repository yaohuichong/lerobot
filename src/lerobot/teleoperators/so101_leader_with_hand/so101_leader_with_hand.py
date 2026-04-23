#!/usr/bin/env python

import logging
from typing import Any

import numpy as np

from lerobot.motors import Motor, MotorNormMode
from lerobot.motors.feetech import FeetechMotorsBus, OperatingMode
from lerobot.teleoperators.teleoperator import Teleoperator
from lerobot.teleoperators.so101_leader import SO101Leader
from lerobot.teleoperators.so101_leader.config_so101_leader import SO101LeaderConfig
from lerobot.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError

logger = logging.getLogger(__name__)


@SO101LeaderConfig.register_subclass("so101_leader_with_hand")
class SO101LeaderWithHandConfig(SO101LeaderConfig):
    hand_port: str = "/dev/ttyCH343USB2"
    
    finger_motor_ids: dict[str, list[int]] = None
    
    gripper_open_position: float = 0.0
    gripper_close_position: float = 100.0
    
    def __post_init__(self):
        super().__post_init__()
        if self.finger_motor_ids is None:
            self.finger_motor_ids = {
                "index": [1, 2],
                "middle": [3, 4],
                "ring": [5, 6],
                "thumb": [7, 8],
            }


class SO101LeaderWithHand(Teleoperator):
    """
    Combined teleoperator: SO101 Leader Arm + AmazingHand.
    
    SO101 Leader controls the 5 arm joints.
    AmazingHand controls the gripper via finger flex.
    """
    
    config_class = SO101LeaderWithHandConfig
    name = "so101_leader_with_hand"
    
    def __init__(self, config: SO101LeaderWithHandConfig):
        super().__init__(config)
        self.config = config
        
        self.arm = SO101Leader(config)
        
        motors = {}
        for finger_name, motor_ids in config.finger_motor_ids.items():
            for i, motor_id in enumerate(motor_ids):
                motor_key = f"{finger_name}_{i+1}"
                motors[motor_key] = Motor(motor_id, "scs0009", MotorNormMode.RANGE_0_100)
        
        self.hand_bus = FeetechMotorsBus(port=config.hand_port, motors=motors)
        self._hand_connected = False
    
    @property
    def action_features(self) -> dict[str, type]:
        return self.arm.action_features
    
    @property
    def feedback_features(self) -> dict[str, type]:
        return self.arm.feedback_features
    
    @property
    def is_connected(self) -> bool:
        return self.arm.is_connected and self._hand_connected
    
    def connect(self, calibrate: bool = True) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")
        
        self.arm.connect(calibrate=calibrate)
        
        self.hand_bus.connect()
        self.hand_bus.disable_torque()
        for motor in self.hand_bus.motors:
            self.hand_bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)
        self._hand_connected = True
        
        logger.info(f"{self} connected.")
    
    @property
    def is_calibrated(self) -> bool:
        return self.arm.is_calibrated
    
    def calibrate(self) -> None:
        self.arm.calibrate()
    
    def configure(self) -> None:
        self.arm.configure()
    
    def get_action(self) -> dict[str, Any]:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")
        
        arm_action = self.arm.get_action()
        
        positions = self.hand_bus.sync_read("Present_Position")
        
        flex_values = []
        for finger_name, motor_ids in self.config.finger_motor_ids.items():
            motor_keys = [f"{finger_name}_{i+1}" for i in range(len(motor_ids))]
            finger_positions = [positions.get(key, 50.0) for key in motor_keys]
            avg_pos = np.mean(finger_positions)
            flex_values.append(avg_pos)
        
        avg_flex = np.mean(flex_values)
        flex_ratio = np.clip(avg_flex / 100.0, 0, 1)
        
        gripper_pos = self.config.gripper_open_position + flex_ratio * (
            self.config.gripper_close_position - self.config.gripper_open_position
        )
        
        action = dict(arm_action)
        action["gripper.pos"] = float(gripper_pos)
        
        return action
    
    def send_feedback(self, feedback: dict[str, float]) -> None:
        self.arm.send_feedback(feedback)
    
    def disconnect(self) -> None:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")
        
        self.arm.disconnect()
        
        if self._hand_connected:
            self.hand_bus.disconnect()
            self._hand_connected = False
        
        logger.info(f"{self} disconnected.")
