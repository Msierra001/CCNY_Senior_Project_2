import pygame
import random
import math

#pip install pygame

# Grid size
ROWS, COLS = 15, 4
CELL_SIZE = 60
WIDTH, HEIGHT = COLS * CELL_SIZE, ROWS * CELL_SIZE
FPS = 1

# Fault types and colors
FAULTS = {'pothole': (139, 69, 19), 'ice': (173, 216, 230), 'rain': (0, 191, 255)}

# Initialize pygame
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Collaborative Autonomous Vehicles")
clock = pygame.time.Clock()

class Vehicle:
    def __init__(self, row, col, vid):
        self.row = row
        self.col = col
        self.id = vid
        self.speed = random.uniform(1, 3)
        self.mass = random.randint(1000, 3000)
        self.yaw = random.uniform(-5, 5)
        self.acceleration = random.uniform(-1, 1)

    def update(self):
        self.row = max(0, self.row - 1)

    def draw(self, ego=False):
        x, y = self.col * CELL_SIZE, self.row * CELL_SIZE
        color = (255, 0, 0) if ego else (0, 255, 0)
        pygame.draw.rect(screen, color, (x + 5, y + 5, CELL_SIZE - 10, CELL_SIZE - 10))

class Environment:
    def __init__(self):
        self.vehicles = []
        self.grid = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.faults = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.spawn_vehicles()

    def spawn_vehicles(self):
        for col in range(COLS):
            v = Vehicle(ROWS - 1, col, col)
            self.vehicles.append(v)
            self.grid[v.row][v.col] = v

    def inject_faults(self):
        self.faults = [[None for _ in range(COLS)] for _ in range(ROWS)]
        for _ in range(3):
            r, c = random.randint(0, ROWS - 2), random.randint(0, COLS - 1)
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
        for v in self.vehicles:
            v.update()

    def draw(self, ego_vehicle):
        screen.fill((50, 50, 50))
        # Draw grid and faults
        for r in range(ROWS):
            for c in range(COLS):
                x, y = c * CELL_SIZE, r * CELL_SIZE
                pygame.draw.rect(screen, (100, 100, 100), (x, y, CELL_SIZE, CELL_SIZE), 1)
                if self.faults[r][c]:
                    pygame.draw.rect(screen, FAULTS[self.faults[r][c]], (x+10, y+10, CELL_SIZE-20, CELL_SIZE-20))

        # Draw vehicles
        for v in self.vehicles:
            v.draw(ego=(v == ego_vehicle))
        pygame.display.flip()

def main():
    env = Environment()
    running = True
    while running:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        env.inject_faults()
        ego_vehicle = env.evaluate_ego()
        env.update()
        env.draw(ego_vehicle)

    pygame.quit()

if __name__ == "__main__":
    main()
