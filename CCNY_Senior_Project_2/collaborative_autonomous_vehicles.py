import pygame
import random

# ----------------------------
# Load config
# ----------------------------
def load_config(path="config.txt"):
    config = {}
    with open(path, 'r') as file:
        for line in file:
            if '=' in line:
                key, value = line.strip().split('=')
                config[key.strip()] = int(value.strip())
    return config

config = load_config()
ROWS = config["ROWS"]
COLS = config["COLS"]
CELL_SIZE = config["CELL_SIZE"]
FPS = config["FPS"]
WIDTH, HEIGHT = COLS * CELL_SIZE, config["VIEW_ROWS"] * CELL_SIZE

SAFE_DISTANCE = 2
MERGE_SAFE_DISTANCE = 2

# Fault visuals
FAULTS = {
    'pothole': (139, 69, 19),
    'ice': (173, 216, 230),
    'rain': (0, 191, 255)
}

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Autonomous Cars (Grid, Dark Road)")
clock = pygame.time.Clock()
camera_offset = 0

# ----------------------------
# Vehicle Class
# ----------------------------
class Vehicle:
    def __init__(self, row, col, vid):
        self.row = row
        self.col = col
        self.id = vid
        self.speed = random.uniform(1, 3)
        self.mass = random.randint(1000, 3000)
        self.yaw = random.uniform(-5, 5)
        self.acceleration = random.uniform(-1, 1)

    def update(self, env):
        next_row = self.row - 1

        for offset in range(1, SAFE_DISTANCE + 1):
            check_row = self.row - offset
            if check_row >= 0 and env.grid[check_row][self.col]:
                self.try_merge(env)
                return

        if next_row >= 0 and env.grid[next_row][self.col] is None:
            env.grid[self.row][self.col] = None
            self.row = next_row
            env.grid[self.row][self.col] = self

    def try_merge(self, env):
        for dir in [-1, 1]:
            new_col = self.col + dir
            if 0 <= new_col < COLS:
                can_merge = True
                for offset in range(-MERGE_SAFE_DISTANCE, MERGE_SAFE_DISTANCE + 1):
                    check_row = self.row + offset
                    if 0 <= check_row < ROWS and env.grid[check_row][new_col]:
                        can_merge = False
                        break
                if can_merge:
                    env.grid[self.row][self.col] = None
                    self.col = new_col
                    env.grid[self.row][self.col] = self
                    return

    def draw(self, ego=False):
        x = self.col * CELL_SIZE
        y = self.row * CELL_SIZE - camera_offset
        if 0 <= y < HEIGHT:
            color = (255, 0, 0) if ego else (0, 255, 0)
            pygame.draw.rect(screen, color, (x + 5, y + 5, CELL_SIZE - 10, CELL_SIZE - 10))

# ----------------------------
# Environment Class
# ----------------------------
class Environment:
    def __init__(self):
        self.vehicles = []
        self.grid = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.faults = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.spawn_vehicles()

    def spawn_vehicles(self):
        # One vehicle per column at the bottom row
        for col in range(COLS):
            v = Vehicle(ROWS - 1, col, col)
            self.vehicles.append(v)
            self.grid[v.row][v.col] = v

    def inject_faults(self):
        self.faults = [[None for _ in range(COLS)] for _ in range(ROWS)]
        for _ in range(20):
            r = random.randint(0, ROWS - 2)
            c = random.randint(0, COLS - 1)
            self.faults[r][c] = random.choice(list(FAULTS.keys()))

    def evaluate_ego(self):
        scores = []
        for v in self.vehicles:
            dist_to_fault = 1
            for dr in range(1, 4):
                r = v.row - dr
                if r >= 0 and self.faults[r][v.col]:
                    dist_to_fault = dr
                    break
            score = (abs(v.yaw) * 2) + (abs(v.acceleration) * 1.5) + (1 / dist_to_fault)
            scores.append((score, v))
        scores.sort(key=lambda x: x[0])
        return scores[0][1]

    def update(self):
        for v in sorted(self.vehicles, key=lambda car: -car.row):
            v.update(self)

    def draw(self, ego_vehicle):
        # Draw dark road
        screen.fill((30, 30, 30))  # Dark background

        # Draw dashed vertical lane lines
        for c in range(1, COLS):
            x = c * CELL_SIZE
            for y in range(0, HEIGHT, 40):
                pygame.draw.line(screen, (150, 150, 150), (x, y), (x, y + 20), 2)

        # Draw faults
        for r in range(ROWS):
            for c in range(COLS):
                y = r * CELL_SIZE - camera_offset
                if y + CELL_SIZE < 0 or y > HEIGHT:
                    continue
                if self.faults[r][c]:
                    x = c * CELL_SIZE
                    pygame.draw.rect(screen, FAULTS[self.faults[r][c]],
                                     (x + 10, y + 10, CELL_SIZE - 20, CELL_SIZE - 20))

        # Draw vehicles
        for v in self.vehicles:
            v.draw(ego=(v == ego_vehicle))

        pygame.display.flip()

# ----------------------------
# Main Loop
# ----------------------------
def main():
    global camera_offset
    env = Environment()
    running = True

    camera_offset = 0

    while running:
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        env.inject_faults()
        ego_vehicle = env.evaluate_ego()
        env.update()

        camera_offset = ego_vehicle.row * CELL_SIZE - HEIGHT // 2
        env.draw(ego_vehicle)

    pygame.quit()

if __name__ == "__main__":
    main()
