"""The shared action envelope for strategy processes and external training actors."""
import json
from .communication import validate_messages
from .worker import ACTIONS_LIMIT

ACTION_FIELDS = {
    'move', 'aim', 'pitch', 'fire', 'power', 'profile', 'buy_ammo', 'remote_heal',
    'revive', 'deploy', 'support', 'altitude', 'pick_unit', 'assembly',
    'assembly_insert', 'assembly_translate', 'assembly_rotate', 'assembly_confirm',
    'rune_start', 'heading', 'crouch', 'rescue', 'yaw_rate', 'brake', 'leg_height',
    'jump', 'lean', 'arm', 'arm2', 'pickup_arm', 'transform', 'install_launcher',
    'assembly_core', 'assembly_lift', 'assembly_flip', 'assembly_rotate2', 'posture',
    'posture_enhanced', 'drones',
}


def validate_actions(actions, controlled, has_messages=True, dynamic=False):
    if not isinstance(actions, dict):
        raise ValueError('Invalid action object')
    if not set(actions) <= set(controlled):
        raise ValueError('Attempt to control an unowned robot')
    if len(json.dumps(actions, allow_nan=False, separators=(',', ':')).encode()) > ACTIONS_LIMIT:
        raise ValueError('Team actions exceed 16 KiB')
    fields = ACTION_FIELDS | ({'messages'} if has_messages else set())
    for slot, action in actions.items():
        if not isinstance(action, dict) or not set(action) <= fields:
            raise ValueError('Action contains unsupported fields')
        if len(json.dumps(action, allow_nan=False).encode()) > 1024:
            raise ValueError('Each robot action must be <=1 KiB')
        if 'messages' in action:
            validate_messages(action['messages'], slot, dynamic)
    return actions
