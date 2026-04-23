#!/usr/bin/env python

# Copyright 2024 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import time
from typing import Any

import numpy as np

from lerobot.errors import DeviceAlreadyConnectedError, DeviceNotConnectedError
from lerobot.motors import Motor, MotorCalibration, MotorNormMode
from lerobot.motors.feetech import (
    FeetechMotorsBus,
    OperatingMode,
)

from ..teleoperator import Teleoperator
from .config_amazing_hand import AmazingHandConfig

logger = logging.getLogger(__name__)


class AmazingHand(Teleoperator):
    """
    AmazingHand teleoperator for dexterous hand control.
    
    This teleoperator reads finger positions from the AmazingHand and provides
    action data that can be used to control a gripper or another dexterous hand.
    
    The hand has 4 fingers, each with 2 motors (8 motors total):
    - Index: configurable motor IDs
    - Middle: configurable motor IDs
    - Ring: configurable motor IDs
    - Thumb: configurable motor IDs
    
    When sharing a serial bus with SO-ARM100 leader arm (motor IDs 1-6),
    configure finger_motor_ids to avoid conflicts, e.g.:
    {
        "index": [11, 12],
        "middle": [13, 14],
        "ring": [15, 16],
        "thumb": [17, 18],
    }
    """

    config_class = AmazingHandConfig
    name = "amazing_hand"

    DEFAULT_FINGER_MOTOR_IDS = {
        "index": [1, 2],
        "middle": [3, 4],
        "ring": [5, 6],
        "thumb": [7, 8],
    }

    def __init__(self, config: AmazingHandConfig):
        super().__init__(config)
        self.config = config
        
        self.finger_motor_ids = config.finger_motor_ids or self.DEFAULT_FINGER_MOTOR_IDS
        
        norm_mode = MotorNormMode.DEGREES if config.use_degrees else MotorNormMode.RANGE_M100_100
        
        motors = {}
        for finger_name, motor_ids in self.finger_motor_ids.items():
            for i, motor_id in enumerate(motor_ids):
                motor_key = f"{finger_name}_{i+1}"
                motors[motor_key] = Motor(motor_id, "scs0009", norm_mode)
        
        self.bus = FeetechMotorsBus(
            port=self.config.port,
            motors=motors,
            calibration=self.calibration,
        )
        
        self._motor_id_to_middle_idx = {}
        for finger_name, motor_ids in self.finger_motor_ids.items():
            for i, motor_id in enumerate(motor_ids):
                sorted_ids = sorted([
                    mid for ids in self.finger_motor_ids.values() for mid in ids
                ])
                self._motor_id_to_middle_idx[motor_id] = sorted_ids.index(motor_id)

    @property
    def action_features(self) -> dict[str, type]:
        features = {}
        for finger_name in self.finger_motor_ids.keys():
            features[f"{finger_name}.flex"] = float
        features["gripper.pos"] = float
        return features

    @property
    def feedback_features(self) -> dict[str, type]:
        return {}

    @property
    def is_connected(self) -> bool:
        return self.bus.is_connected

    def connect(self, calibrate: bool = True) -> None:
        if self.is_connected:
            raise DeviceAlreadyConnectedError(f"{self} already connected")

        self.bus.connect()
        if not self.is_calibrated and calibrate:
            logger.info(
                "Mismatch between calibration values in the motor and the calibration file or no calibration file found"
            )
            self.calibrate()

        self.configure()
        logger.info(f"{self} connected.")

    @property
    def is_calibrated(self) -> bool:
        return self.bus.is_calibrated

    def calibrate(self) -> None:
        if self.calibration:
            user_input = input(
                f"Press ENTER to use provided calibration file associated with the id {self.id}, "
                f"or type 'c' and press ENTER to run calibration: "
            )
            if user_input.strip().lower() != "c":
                logger.info(f"Writing calibration file associated with the id {self.id} to the motors")
                self.bus.write_calibration(self.calibration)
                return

        logger.info(f"\nRunning calibration of {self}")
        self.bus.disable_torque()
        for motor in self.bus.motors:
            self.bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)

        input(f"Move {self} to the middle of its range of motion and press ENTER....")
        homing_offsets = self.bus.set_half_turn_homings()

        unknown_range_motors = list(self.bus.motors.keys())
        print(
            f"Move all finger joints sequentially through their "
            "entire ranges of motion.\nRecording positions. Press ENTER to stop..."
        )
        range_mins, range_maxes = self.bus.record_ranges_of_motion(unknown_range_motors)

        self.calibration = {}
        for motor, m in self.bus.motors.items():
            self.calibration[motor] = MotorCalibration(
                id=m.id,
                drive_mode=0,
                homing_offset=homing_offsets[motor],
                range_min=range_mins[motor],
                range_max=range_maxes[motor],
            )

        self.bus.write_calibration(self.calibration)
        self._save_calibration()
        print(f"Calibration saved to {self.calibration_fpath}")

    def configure(self) -> None:
        self.bus.disable_torque()
        self.bus.configure_motors()
        for motor in self.bus.motors:
            self.bus.write("Operating_Mode", motor, OperatingMode.POSITION.value)

    def setup_motors(self) -> None:
        for motor in reversed(self.bus.motors):
            input(f"Connect the controller board to the '{motor}' motor only and press enter.")
            self.bus.setup_motor(motor)
            print(f"'{motor}' motor id set to {self.bus.motors[motor].id}")

    def get_action(self) -> dict[str, float]:
        start = time.perf_counter()
        
        positions = self.bus.sync_read("Present_Position")
        
        action = {}
        for finger_name, motor_ids in self.finger_motor_ids.items():
            motor_keys = [f"{finger_name}_{i+1}" for i in range(len(motor_ids))]
            finger_positions = [positions.get(key, 0.0) for key in motor_keys]
            
            if self.config.use_degrees:
                middle_offsets = []
                for motor_id in motor_ids:
                    idx = self._motor_id_to_middle_idx.get(motor_id, 0)
                    if idx < len(self.config.middle_positions):
                        middle_offsets.append(self.config.middle_positions[idx])
                    else:
                        middle_offsets.append(0.0)
                relative_positions = [p - o for p, o in zip(finger_positions, middle_offsets)]
            else:
                relative_positions = finger_positions
            
            flex = np.mean(relative_positions)
            action[f"{finger_name}.flex"] = float(flex)
        
        avg_flex = np.mean([action[f"{fn}.flex"] for fn in self.finger_motor_ids.keys()])
        
        if self.config.use_degrees:
            flex_ratio = np.clip(avg_flex / 90.0, 0, 1)
        else:
            flex_ratio = np.clip((avg_flex + 1) / 2, 0, 1)
        
        gripper_pos = self.config.gripper_open_position + flex_ratio * (
            self.config.gripper_close_position - self.config.gripper_open_position
        )
        action["gripper.pos"] = float(gripper_pos)
        
        dt_ms = (time.perf_counter() - start) * 1e3
        logger.debug(f"{self} read action: {dt_ms:.1f}ms")
        
        return action

    def get_finger_positions(self) -> dict[str, list[float]]:
        positions = self.bus.sync_read("Present_Position")
        
        finger_positions = {}
        for finger_name, motor_ids in self.finger_motor_ids.items():
            motor_keys = [f"{finger_name}_{i+1}" for i in range(len(motor_ids))]
            finger_positions[finger_name] = [positions.get(key, 0.0) for key in motor_keys]
        
        return finger_positions

    def get_average_flex_ratio(self) -> float:
        action = self.get_action()
        flex_values = [action[f"{fn}.flex"] for fn in self.finger_motor_ids.keys()]
        avg_flex = np.mean(flex_values)
        
        if self.config.use_degrees:
            return float(np.clip(avg_flex / 90.0, 0, 1))
        else:
            return float(np.clip((avg_flex + 1) / 2, 0, 1))

    def send_feedback(self, feedback: dict[str, float]) -> None:
        raise NotImplementedError("AmazingHand does not support force feedback yet.")

    def disconnect(self) -> None:
        if not self.is_connected:
            raise DeviceNotConnectedError(f"{self} is not connected.")

        self.bus.disconnect()
        logger.info(f"{self} disconnected.")
