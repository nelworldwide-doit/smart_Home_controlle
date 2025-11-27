import asyncio
from datetime import datetime

import flet as ft
from flet import TemplateRoute


def main(page: ft.Page):
    page.title = "Smart Home Controller + Simulator"
    page.bgcolor = ft.Colors.BLUE_GREY_50
    page.padding = 20

    #
    # 1) Simple in-memory "database" for devices & logs
    # 
    devices = {
        "light1": {
            "id": "light1",
            "name": "Living Room Light",
            "type": "light",
            "is_on": False,
        },
        "fan1": {
            "id": "fan1",
            "name": "Ceiling Fan",
            "type": "fan",
            "speed": 0,  # 0..3
        },
        "thermo1": {
            "id": "thermo1",
            "name": "Thermostat",
            "type": "thermostat",
            "setpoint": 22.0,  # °C
        },
        "door1": {
            "id": "door1",
            "name": "Front Door",
            "type": "door",
            "locked": True,
        },
    }

    # List of action logs: each item is {timestamp, device_id, action, user}
    logs = []

    # Power history: list of (time_index, total_power)
    power_history = []

    # These will be created when /statistics page is opened
    log_table = None
    power_chart = None

    # 
    # 2) Helper functions: logging + power model
    # 

    def publish_log(device_id: str, action: str):
        """Send a log message through pubsub."""
        msg = {
            "type": "log",
            "device_id": device_id,
            "action": action,
            "user": "User",  # later: replace with real username
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
        page.pubsub.send_all(msg)

    def compute_total_power() -> float:
        """
        Very simple power model (fake numbers):
        - Light: 40 W when ON
        - Fan:   speed * 20 W
        - Thermostat: 500 W if setpoint > 20°C
        - Door: 0 W (just a lock)
        """
        total = 0.0

        light = devices["light1"]
        fan = devices["fan1"]
        thermo = devices["thermo1"]

        if light["is_on"]:
            total += 40.0

        total += fan["speed"] * 20.0

        if thermo["setpoint"] > 20.0:
            total += 500.0

        return total

    # 
    # 3) Chart update helper
    # 

    def update_power_chart():
        """Rebuild line chart data from power_history."""
        nonlocal power_chart

        # Chart not created yet
        if power_chart is None:
            return

        # Chart exists but is not attached to a page yet
        if power_chart.page is None:
            return

        if not power_history:
            return

        points = [
            ft.LineChartDataPoint(t, p) for t, p in power_history
        ]
        max_power = max(p for _, p in power_history)

        power_chart.data_series = [
            ft.LineChartData(
                data_points=points,
                stroke_width=2,
            )
        ]
        power_chart.min_x = power_history[0][0]
        power_chart.max_x = power_history[-1][0]
        power_chart.min_y = 0
        power_chart.max_y = max_power + 50  # small headroom

        power_chart.update()

    # 
    # 4) Pub/Sub subscriber: receives logs & power samples
    # 

    def handle_message(msg):
        nonlocal log_table, power_chart

        if not isinstance(msg, dict):
            return

        if msg.get("type") == "log":
            # Save log
            logs.append(msg)

            # If log table is visible, add a row
            if log_table is not None:
                log_table.rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(msg["timestamp"])),
                            ft.DataCell(ft.Text(msg["device_id"])),
                            ft.DataCell(ft.Text(msg["action"])),
                            ft.DataCell(ft.Text(msg["user"])),
                        ]
                    )
                )
                log_table.update()

        elif msg.get("type") == "power_sample":
            # Save power sample (keep last 50)
            t = msg["time"]
            p = msg["total_power"]
            power_history.append((t, p))
            if len(power_history) > 50:
                power_history.pop(0)

            # Update chart if visible
            if power_chart is not None:
                update_power_chart()

    page.pubsub.subscribe(handle_message)

    # 
    # 5) Background simulator task (async)
    # 

    async def simulator_task():
        """Runs forever, sends power usage samples every 2 seconds."""
        t = 0
        while True:
            total_power = compute_total_power()
            msg = {
                "type": "power_sample",
                "time": t,
                "total_power": total_power,
            }
            page.pubsub.send_all(msg)

            t += 1
            await asyncio.sleep(2)

    # IMPORTANT: give the FUNCTION, no parentheses
    page.run_task(simulator_task)

    # 
    # 6) Card factories (re-usable widgets)
    # 

    def create_light_card():
        """Living room light card (ON/OFF)."""

        status_text = ft.Text("Status: OFF")
        helper_text = ft.Text("Tap to switch the light.")

        def toggle_light(e):
            light = devices["light1"]
            light["is_on"] = not light["is_on"]

            if light["is_on"]:
                status_text.value = "Status: ON"
                e.control.text = "Turn OFF"
                publish_log("light1", "Turn ON")
            else:
                status_text.value = "Status: OFF"
                e.control.text = "Turn ON"
                publish_log("light1", "Turn OFF")

            status_text.update()
            e.control.update()

        button = ft.ElevatedButton("Turn ON", on_click=toggle_light)

        details_button = ft.TextButton(
            "Details",
            on_click=lambda e: page.go("/device/light1"),
        )

        return ft.Container(
            bgcolor=ft.Colors.AMBER_50,
            border_radius=16,
            padding=20,
            width=360,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.LIGHTBULB, size=30),
                            ft.Text(
                                "Living Room Light",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=10,
                    ),
                    status_text,
                    helper_text,
                    ft.Row(
                        controls=[details_button, button],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=8,
            ),
        )

    def create_fan_card():
        """Ceiling fan card (speed 0..3)."""

        speed_text = ft.Text("Fan speed: 0")
        helper_text = ft.Text("0 = OFF, 3 = MAX.")

        def on_change(e):
            value = int(e.control.value)
            devices["fan1"]["speed"] = value
            speed_text.value = f"Fan speed: {value}"
            speed_text.update()
            publish_log("fan1", f"Set speed {value}")

        slider = ft.Slider(
            min=0,
            max=3,
            divisions=3,
            value=0,
            on_change=on_change,
        )

        details_button = ft.TextButton(
            "Details",
            on_click=lambda e: page.go("/device/fan1"),
        )

        return ft.Container(
            bgcolor=ft.Colors.CYAN_50,
            border_radius=16,
            padding=20,
            width=360,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.AIR, size=30),
                            ft.Text(
                                "Ceiling Fan",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=10,
                    ),
                    speed_text,
                    helper_text,
                    slider,
                    ft.Row(
                        controls=[details_button],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=8,
            ),
        )

    def create_thermostat_card():
        """Thermostat card (setpoint slider)."""

        setpoint_text = ft.Text("Set point: 22.0 °C")
        helper_text = ft.Text("Use slider to change temperature.")

        def on_change(e):
            value = e.control.value
            devices["thermo1"]["setpoint"] = value
            setpoint_text.value = f"Set point: {value:.1f} °C"
            setpoint_text.update()
            publish_log("thermo1", f"Set {value:.1f} °C")

        slider = ft.Slider(
            min=10,
            max=30,
            value=22,
            on_change=on_change,
        )

        details_button = ft.TextButton(
            "Details",
            on_click=lambda e: page.go("/device/thermo1"),
        )

        return ft.Container(
            bgcolor=ft.Colors.RED_50,
            border_radius=16,
            padding=20,
            width=360,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.DEVICE_THERMOSTAT, size=30),
                            ft.Text(
                                "Thermostat",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=10,
                    ),
                    setpoint_text,
                    helper_text,
                    slider,
                    ft.Row(
                        controls=[details_button],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                ],
                spacing=8,
            ),
        )

    def create_door_card():
        """Door lock card (LOCK/UNLOCK)."""

        status_text = ft.Text("Door: LOCKED")
        helper_text = ft.Text("Tap to lock / unlock the door.")

        def toggle_door(e):
            door = devices["door1"]
            door["locked"] = not door["locked"]

            if door["locked"]:
                status_text.value = "Door: LOCKED"
                e.control.text = "Unlock"
                publish_log("door1", "Lock")
            else:
                status_text.value = "Door: UNLOCKED"
                e.control.text = "Lock"
                publish_log("door1", "Unlock")

            status_text.update()
            e.control.update()

        button = ft.ElevatedButton("Unlock", on_click=toggle_door)

        details_button = ft.TextButton(
            "Details",
            on_click=lambda e: page.go("/device/door1"),
        )

        return ft.Container(
            bgcolor=ft.Colors.BROWN_50,
            border_radius=16,
            padding=20,
            width=360,
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.DOOR_FRONT_DOOR, size=30),
                            ft.Text(
                                "Front Door",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                            ),
                        ],
                        spacing=10,
                    ),
                    status_text,
                    helper_text,
                    ft.Row(
                        controls=[details_button, button],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                ],
                spacing=8,
            ),
        )

    # 
    # 7) Top navigation bar (shown on all pages)
    # 

    def build_appbar(current_route: str) -> ft.AppBar:
        """Simple navigation using AppBar buttons."""

        def go_overview(e):
            page.go("/overview")

        def go_stats(e):
            page.go("/statistics")

        return ft.AppBar(
            title=ft.Text("Smart Home Controller"),
            center_title=False,
            bgcolor=ft.Colors.WHITE,
            actions=[
                ft.TextButton(
                    "Overview",
                    on_click=go_overview,
                    style=ft.ButtonStyle(
                        color=ft.Colors.BLUE
                        if current_route.startswith("/overview")
                        else ft.Colors.BLACK,
                    ),
                ),
                ft.TextButton(
                    "Statistics",
                    on_click=go_stats,
                    style=ft.ButtonStyle(
                        color=ft.Colors.BLUE
                        if current_route.startswith("/statistics")
                        else ft.Colors.BLACK,
                    ),
                ),
            ],
        )

    # 
    # 8) Route handling (multi-page navigation)
    #

    def route_change(route):
        nonlocal log_table, power_chart

        page.views.clear()
        tr = TemplateRoute(page.route)

        # Overview page 
        if tr.match("/overview"):
            view = ft.View(
                route="/overview",
                appbar=build_appbar("/overview"),
                controls=[
                    ft.Text(
                        "On/Off devices",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        controls=[
                            create_light_card(),
                            create_door_card(),
                        ],
                        wrap=True,
                        spacing=20,
                    ),
                    ft.Divider(),
                    ft.Text(
                        "Slider controlled devices",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Row(
                        controls=[
                            create_thermostat_card(),
                            create_fan_card(),
                        ],
                        wrap=True,
                        spacing=20,
                    ),
                ],
                padding=20,
                bgcolor=ft.Colors.BLUE_GREY_50,
            )
            page.views.append(view)

        #  Device details page 
        elif tr.match("/device/:id"):
            dev_id = tr.id
            dev = devices.get(dev_id)

            if dev is None:
                title = "Unknown device"
                info_rows = [ft.Text("Device not found.")]
            else:
                title = f"{dev['name']} details"
                info_rows = [
                    ft.Text(f"ID: {dev['id']}"),
                    ft.Text(f"Type: {dev['type']}"),
                ]
                if dev["type"] == "light":
                    info_rows.append(
                        ft.Text(f"State: {'ON' if dev['is_on'] else 'OFF'}")
                    )
                elif dev["type"] == "fan":
                    info_rows.append(ft.Text(f"Speed: {dev['speed']}"))
                elif dev["type"] == "thermostat":
                    info_rows.append(
                        ft.Text(f"Setpoint: {dev['setpoint']:.1f} °C")
                    )
                elif dev["type"] == "door":
                    info_rows.append(
                        ft.Text(
                            f"Locked: {'YES' if dev['locked'] else 'NO'}"
                        )
                    )

            device_logs = [log for log in logs if log["device_id"] == dev_id]
            log_controls = [
                ft.Text(
                    f"{log['timestamp']} - {log['action']} ({log['user']})"
                )
                for log in device_logs
            ]

            view = ft.View(
                route=f"/device/{dev_id}",
                appbar=build_appbar("/device"),
                controls=[
                    ft.Text(
                        title,
                        size=24,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Column(controls=info_rows, spacing=5),
                    ft.Divider(),
                    ft.Text(
                        "Recent actions",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Column(
                        controls=log_controls
                        or [ft.Text("No actions yet.")],
                        spacing=2,
                    ),
                    ft.ElevatedButton(
                        "Back to overview",
                        on_click=lambda e: page.go("/overview"),
                    ),
                ],
                padding=20,
                bgcolor=ft.Colors.BLUE_GREY_50,
            )
            page.views.append(view)

        #  Statistics page 
        elif tr.match("/statistics"):
            # Build DataTable from current logs
            log_table = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Time")),
                    ft.DataColumn(ft.Text("Device")),
                    ft.DataColumn(ft.Text("Action")),
                    ft.DataColumn(ft.Text("User")),
                ],
                rows=[
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(log["timestamp"])),
                            ft.DataCell(ft.Text(log["device_id"])),
                            ft.DataCell(ft.Text(log["action"])),
                            ft.DataCell(ft.Text(log["user"])),
                        ]
                    )
                    for log in logs
                ],
            )

            # Initial empty chart; data will be filled later
            power_chart = ft.LineChart(
                data_series=[],
                border=ft.border.all(1, ft.Colors.GREY),
                horizontal_grid_lines=ft.ChartGridLines(
                    color=ft.Colors.GREY_300,
                    width=0.5,
                ),
                vertical_grid_lines=ft.ChartGridLines(
                    color=ft.Colors.GREY_300,
                    width=0.5,
                ),
                min_x=0,
                max_x=10,
                min_y=0,
                max_y=100,
                animate=True,
                expand=True,
            )

            view = ft.View(
                route="/statistics",
                appbar=build_appbar("/statistics"),
                controls=[
                    ft.Text(
                        "Power consumption (simulated)",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Container(
                        content=power_chart,
                        height=300,
                        padding=10,
                    ),
                    ft.Divider(),
                    ft.Text(
                        "Action log",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                    ),
                    ft.Container(
                        content=log_table,
                        bgcolor=ft.Colors.WHITE,
                        border_radius=12,
                        padding=10,
                    ),
                ],
                padding=20,
                bgcolor=ft.Colors.BLUE_GREY_50,
            )

            # Add view to page first
            page.views.append(view)
            page.update()

            # Now chart is attached to page → safe to update
            update_power_chart()

        page.update()

    def view_pop(view):
        page.views.pop()
        if page.views:
            top_view = page.views[-1]
            page.go(top_view.route)

    page.on_route_change = route_change
    page.on_view_pop = view_pop

    # Start at overview page
    page.go("/overview")


ft.app(target=main)