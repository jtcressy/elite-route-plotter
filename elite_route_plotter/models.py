import time
from tabulate import tabulate
import requests


class StarSystem:
    def __init__(self, name, x, y, z, is_neutron=False):
        self.name = name
        self.x = x
        self.y = y
        self.z = z
        self.is_neutron = is_neutron


class RouteWaypoint(StarSystem):
    def __init__(self, w):
        super().__init__(
            w['system'],
            w['x'], w['y'], w['z'],
            bool(w['neutron_star'])
        )
        self.distance_jumped = w['distance_jumped']
        self.distance_left = w['distance_left']
        self.jumps = w['jumps']
        self.visited = False


class RouteMeta:
    def __init__(self, route):
        self.src = route.src
        self.dest = route.dest
        self.eff = route.eff
        self.jump_range = route.jump_range
        self.distance = route.distance
        self.next = route.next_waypoint
        self.current = route.current_waypoint
        self.remaining_jumps = route.remaining_jumps


class Route:
    def __init__(self, waypoints: list, src, dest, eff, jump_range, distance, total_jumps, via):
        self.waypoints = waypoints
        self.total_jumps = total_jumps
        self.via = via
        self.src = src
        self.dest = dest
        self.eff = eff
        self.jump_range = jump_range
        self.distance = distance
        self.paused = False  # Used by the pause button to halt the queue of system names

    @property
    def next_waypoint(self):
        items = [w for w in self.waypoints if not w.visited]
        if len(items) > 0:
            return items[0]
        else:
            return None

    @property
    def current_waypoint(self):
        items = [w for w in self.waypoints if w.visited]
        if len(items) > 0:
            return items[-1]
        else:
            return None

    @property
    def remaining_jumps(self):
        return sum([int(w.jumps) for w in self.waypoints if not w.visited])

    def visit(self, idx):
        self.waypoints[idx].visited = True

    def cancel_visit(self, idx):
        self.waypoints[idx].visited = False

    def __str__(self):
        output = "Route Summary\n\n"
        output += tabulate(
            [
                [
                    self.src.title(),
                    self.dest.title(),
                    self.distance,
                    self.total_jumps
                ]
            ],
            ["Source System", "Destination System", "Total Distance (LY)", "Total Jumps"]
        )
        output += "\n\n"
        output += tabulate(
            [
                [w.name, w.distance_jumped, w.distance_left, w.jumps]
                for w in self.waypoints
            ],
            ["System Name", "Distance (LY)", "Remaining(LY)", "Jumps"]
        )
        output += "\n"
        return output

    @classmethod
    def create(cls, src, dest, jump_range, eff='60', timeout=10):
        """Create a Route() from source (src) to destination (dest) with a jump range of (jump_range) """
        request_url = f"https://spansh.co.uk/api/route?efficiency={eff}&from={src}&to={dest}&range={jump_range}"
        result = requests.post(request_url).json()
        job_id = result['job']
        elapsed = 0
        while True:
            response_url = f"https://spansh.co.uk/api/results/{job_id}"
            response = requests.get(response_url).json()
            if response['status'] == 'ok':
                new_route = cls(
                    [RouteWaypoint(w) for w in response['result']['system_jumps']],
                    response['result']['source_system'],
                    response['result']['destination_system'],
                    response['result']['efficiency'],
                    response['result']['range'],
                    response['result']['distance'],
                    response['result']['total_jumps'],
                    response['result']['via']
                )
                new_route.visit(0)  # because waypoint 0 is where we started, thus we're already there
                return new_route
            time.sleep(1)
            elapsed += 1
            if elapsed >= timeout:
                raise TimeoutError(f"Route job exceeded timeout of {timeout}s")
