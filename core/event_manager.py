# Copyright 2024 The Lynx Authors. All rights reserved.
# Licensed under the Apache License Version 2.0 that can be found in the
# LICENSE file in the root directory of this source tree.

import logging

from core.event import Event
from core.lifecycle import TaskResult, TaskTerminalStatus


class ThreadingEventManager:

    def __init__(self):
        self._event_consumers = {}
        self._event_results = {}

    def clear(self):
        for k, event_list in self._event_consumers.items():
            for e in event_list:
                result = TaskResult(k, status=TaskTerminalStatus.CANCELLED, reason="event_manager_clear")
                self._event_results[k] = result
                e.complete(result)
        self._event_consumers.clear()

    def register_consumer(self, event_name) -> Event:
        assert isinstance(event_name, str), "event_name can only be str"
        logging.debug(f"register consumer for event {event_name}")
        event = Event(event_name, self._event_results.get(event_name))
        if event.is_set():
            return event
        event_list = self._event_consumers.get(event_name, [])
        event_list.append(event)
        self._event_consumers[event_name] = event_list
        return event

    def produce_event(self, event_name, result):
        logging.debug(f"produce event {event_name}")
        self._event_results[event_name] = result
        if event_name not in self._event_consumers:
            logging.debug(f"no consumers found for event: {event_name}")
            return
        for event in self._event_consumers[event_name]:
            event.complete(result)
        self._event_consumers[event_name].clear()

    def get_results(self):
        return dict(self._event_results)
