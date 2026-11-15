"""Automatic attention updates use fake I/O and preserve mounted controls."""

import asyncio

from orcan_cockpit import jobs_modal, rail
from orcan_cockpit.app import CockpitApp
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Button


async def main():
    calls = 0
    gate = asyncio.Event()
    extra_job = False
    async def overview():
        nonlocal calls
        calls += 1
        await gate.wait()
        value = {'jobs': [{'id': 'one', 'repo': '/tmp/auto-project', 'sha': '123',
                          'status': 'failed', 'task': 'Check\n' * 100, 'profile': 'test',
                          'acknowledged': None}]}
        if extra_job:
            value['jobs'].insert(0, {'id': 'two', 'repo': '/tmp/other-project', 'sha': '456',
                                    'status': 'failed', 'task': 'Other', 'profile': 'test',
                                    'acknowledged': None})
        return value
    jobs_modal.read_overview = overview
    class FastJobs(jobs_modal.JobsModal):
        REFRESH_SECONDS = 0.05
    app = App()
    async with app.run_test(size=(120, 40)) as pilot:
        modal = FastJobs([{'name': 'Auto', 'session': 'auto',
                           'projects': [{'path': '/tmp/auto-project'}]},
                          {'name': 'Other', 'session': 'other',
                           'projects': [{'path': '/tmp/other-project'}]}])
        await app.push_screen(modal)
        await pilot.pause(0.2)
        assert calls == 1  # Slow I/O must not be cancelled or duplicated by timers.
        gate.set()
        await pilot.pause(0.15)
        button = modal.query_one('#jobs-workspace-0', Button)
        button.focus()
        await pilot.pause(0.15)
        assert calls >= 2
        assert modal.query_one('#jobs-workspace-0', Button) is button
        assert button.has_focus
        extra_job = True
        await pilot.pause(0.15)
        assert modal.query_one('#jobs-workspace-0', Button) is button
        assert button.has_focus
        assert modal._targets['jobs-workspace-0']['session'] == 'auto'
        assert modal._targets['jobs-workspace-1']['session'] == 'other'
        extra_job = False
        await pilot.pause(0.15)
        assert modal.query_one('#jobs-workspace-0', Button) is button
        assert button.has_focus
        assert not modal.query('#jobs-workspace-1')
        scroll = modal.query_one(VerticalScroll)
        scroll.scroll_to(y=10, animate=False, force=True)
        await pilot.pause(0.1)
        offset = scroll.scroll_y
        assert offset > 0
        await pilot.pause(0.15)
        assert scroll.scroll_y == offset
        await pilot.press('escape')
        await pilot.pause(0.1)
        stopped = calls
        await pilot.pause(0.15)
        assert calls == stopped

    pulse_calls = 0
    pulse_gate = asyncio.Event()
    state = {'attention_count': 2, 'storage': {'ready': False}}
    offline = False
    async def pulse():
        nonlocal pulse_calls
        pulse_calls += 1
        await pulse_gate.wait()
        if offline:
            raise OSError('offline')
        return state
    rail.read_pulse = pulse
    class FastRail(rail.UtilityRail):
        REFRESH_SECONDS = 0.05
    class RailApp(App):
        CSS = CockpitApp.CSS
        def compose(self) -> ComposeResult:
            yield FastRail(id="rail")
    app = RailApp()
    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause(0.2)
        assert pulse_calls == 1
        pulse_gate.set()
        await pilot.pause(0.1)
        widget = app.query_one(FastRail)
        button = widget.query_one('#rail-jobs', Button)
        assert str(button.label) == 'Tasks · 2 !'
        assert 'Low disk space' in button.tooltip
        assert button.styles.color.hex == '#FBBF24'
        state = {'attention_count': 0, 'storage': {'ready': True}}
        await pilot.pause(0.15)
        assert str(button.label) == 'Tasks · 0'
        assert button.styles.color.hex != '#FBBF24'
        offline = True
        await pilot.pause(0.15)
        assert str(button.label) == 'Tasks · ?'
        offline = False
        await pilot.pause(0.15)
        assert str(button.label) == 'Tasks · 0'
        await widget.remove()
        stopped = pulse_calls
        await pilot.pause(0.15)
        assert pulse_calls == stopped


if __name__ == '__main__':
    asyncio.run(main())
