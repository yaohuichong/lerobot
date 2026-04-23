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

from dataclasses import dataclass, field
from typing import Literal

from ..config import TeleoperatorConfig


@TeleoperatorConfig.register_subclass("amazing_hand")
@dataclass
class AmazingHandConfig(TeleoperatorConfig):
    port: str

    side: Literal["left", "right"] = "right"

    finger_motor_ids: dict[str, list[int]] = field(
        default_factory=lambda: {
            "index": [1, 2],
            "middle": [3, 4],
            "ring": [5, 6],
            "thumb": [7, 8],
        }
    )

    middle_positions: list[float] = field(
        default_factory=lambda: [3.0, 0.0, -5.0, -8.0, -2.0, 5.0, -12.0, 0.0]
    )

    gripper_motor_id: int = 6

    gripper_open_position: float = 0.0
    gripper_close_position: float = -90.0

    use_degrees: bool = True
