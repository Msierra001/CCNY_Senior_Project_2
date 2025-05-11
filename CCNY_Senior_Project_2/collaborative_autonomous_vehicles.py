import pygame
import random
import copy
import math
import time 

# ----------------------------
# Load config
# ----------------------------
def load_config(path="config.txt"):
    config = {}
    try:
        with open(path, 'r') as file:
            for line in file:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, value = line.strip().split('=')
                    key = key.strip()
                    value = value.strip()
                    try:
                        config[key] = int(value)
                    except ValueError:
                        try:
                            config[key] = float(value)
                        except ValueError:
                            config[key] = value
    except FileNotFoundError:
        print(f"Config file '{path}' not found. Creating one with default values.")
        default_config = {
            "ROWS": 100,
            "COLS": 4,
            "CELL_SIZE": 40,
            "FPS": 30,
            "VIEW_ROWS": 15,
            "POTHOLE_CHANCE": 5,
            "ICE_CHANCE": 3,
            "RAIN_CHANCE": 8,
            "WEATHER_CHANGE_CHANCE": 2,
            "RAIN_DURATION": 20,
            "MIN_VEHICLE_DISTANCE": 3,
            "MAX_VEHICLE_DISTANCE": 8,
            "VEHICLE_SPAWN_CHANCE": 40,
            "SAFETY_WEIGHT": 5.0,
            "EFFICIENCY_WEIGHT": 3.0,
            "COMFORT_WEIGHT": 2.0,
            "ANIMATION_STEPS": 10,
            "NUM_CARS_SPAWN": 4,
            "LANE_CHANGE_COOLDOWN": 10
        }
        with open(path, 'w') as file:
            for key, value in default_config.items():
                file.write(f"{key} = {value}\n")
        config = default_config
    return config

# Load configuration
config = load_config()
ROWS = config["ROWS"]
COLS = config["COLS"]
CELL_SIZE = config["CELL_SIZE"]
FPS = config["FPS"]
LEFT_MARGIN = 40 # Left margin for leftmost lane. Adding space for row numbers
RIGHT_MARGIN = 415 # Right margin for rightmost lane. Adding space for the car
WIDTH = LEFT_MARGIN + COLS * CELL_SIZE + RIGHT_MARGIN
HEIGHT = config["VIEW_ROWS"] * CELL_SIZE
ANIMATION_STEPS = config.get("ANIMATION_STEPS", 10)
NUM_CARS_SPAWN = config.get("NUM_CARS_SPAWN", 4)

SAFE_DISTANCE = 2
MERGE_SAFE_DISTANCE = 2
FAULT_DETECTION_DISTANCE = 6

FAULTS = {
    'pothole': (139, 69, 19),
    'rain': (0, 191, 255)
}

FAULT_EFFECTS = {
    'pothole': {'speed_multiplier': 0.7, 'damage': 10},
    'rain': {'speed_multiplier': 0.8, 'visibility': 0.7, 'slip_chance': 0.3}
}

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Autonomous Cars (Smooth Movement)")
clock = pygame.time.Clock()
camera_offset = 0

car_img = pygame.image.load("pngs/car.png").convert_alpha()
car_img = pygame.transform.scale(car_img, (CELL_SIZE - 10, CELL_SIZE - 10))
car_img = pygame.transform.rotate(car_img, +270)

ego_car_img = pygame.image.load("pngs/car_ego.png").convert_alpha()
ego_car_img = pygame.transform.scale(ego_car_img, (CELL_SIZE - 10, CELL_SIZE - 10))
ego_car_img = pygame.transform.rotate(ego_car_img, +270)

alert_img = pygame.Surface((20, 20), pygame.SRCALPHA)
pygame.draw.polygon(alert_img, (255, 255, 0), [(10, 0), (20, 20), (0, 20)])
pygame.draw.polygon(alert_img, (0, 0, 0), [(10, 0), (20, 20), (0, 20)], 2)
pygame.draw.line(alert_img, (0, 0, 0), (10, 5), (10, 12), 2)
pygame.draw.line(alert_img, (0, 0, 0), (10, 15), (10, 16), 2)

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
        self.happiness_history = []
        
        # Animation properties
        self.visual_row = float(row)
        self.visual_col = float(col)
        self.target_row = row
        self.target_col = col
        self.animation_progress = 0
        self.is_changing_lane = False
        
        # Fault reaction properties
        self.reacting_to_fault = None
        self.reaction_time = 0
        self.planned_lane_change = None
        self.last_fault_position = None
        self.lane_change_cooldown = 0


    def detect_faults_ahead(self, env):
        # Look for faults ahead in the current lane
        for offset in range(1, FAULT_DETECTION_DISTANCE + 1):
            check_row = self.row - offset
            if check_row >= 0 and check_row < ROWS:
                fault = env.faults[check_row][self.col]
                if fault:
                    return {'type': fault, 'distance': offset, 'row': check_row, 'col': self.col}
                    
        # Also check diagonally (potholes can span across lanes partially)
        if self.col > 0:  # Check left diagonal
            for offset in range(1, FAULT_DETECTION_DISTANCE + 1):
                check_row = self.row - offset
                check_col = self.col - 1
                if check_row >= 0 and check_row < ROWS:
                    fault = env.faults[check_row][check_col]
                    if fault == 'pothole':  # Only potholes can affect adjacent lanes
                        # Calculate distance (diagonal is further)
                        diag_distance = math.sqrt(offset**2 + 1)
                        return {'type': fault, 'distance': diag_distance, 'row': check_row, 'col': check_col}
                        
        if self.col < COLS - 1:  # Check right diagonal
            for offset in range(1, FAULT_DETECTION_DISTANCE + 1):
                check_row = self.row - offset
                check_col = self.col + 1
                if check_row >= 0 and check_row < ROWS:
                    fault = env.faults[check_row][check_col]
                    if fault == 'pothole':  # Only potholes can affect adjacent lanes
                        # Calculate distance (diagonal is further)
                        diag_distance = math.sqrt(offset**2 + 1)
                        return {'type': fault, 'distance': diag_distance, 'row': check_row, 'col': check_col}
                        
        return None

    def evaluate_lane_safety(self, env, new_col):
        # Check if the lane change is safe
        if not (0 <= new_col < COLS):
            return False
            
        # Check for obstacles in target lane
        for offset in range(-MERGE_SAFE_DISTANCE, MERGE_SAFE_DISTANCE + 1):
            check_row = self.row + offset
            if 0 <= check_row < ROWS and env.grid[check_row][new_col]:
                return False
        
        # Enhanced check for other vehicles - look at relative speeds and positions
        # Check ahead in target lane
        ahead_safe = True
        for offset in range(1, 10):  # Look 10 cells ahead
            check_row = self.row - offset
            if 0 <= check_row < ROWS and env.grid[check_row][new_col]:
                # Found a vehicle ahead in target lane
                other_vehicle = env.grid[check_row][new_col]
                
                # Calculate happiness scores
                my_happiness = self.calculate_happiness(env)
                other_happiness = other_vehicle.calculate_happiness(env)
                
                # If other vehicle is slower than us, we need more distance
                if other_vehicle.speed < self.speed:
                    needed_distance = max(3, 5 * (self.speed - other_vehicle.speed))
                    # If we have lower happiness, we get priority and need less distance
                    if my_happiness < other_happiness:
                        needed_distance = max(2, needed_distance * 0.7)  # 30% reduction in needed distance
                    if offset < needed_distance:
                        ahead_safe = False
                else:
                    # If moving similar speed, still need some distance
                    # But if we have lower happiness, we get priority
                    if my_happiness < other_happiness:
                        if offset < 2:  # Reduced minimum distance for lower happiness
                            ahead_safe = False
                    else:
                        if offset < 3:
                            ahead_safe = False
                break
        
        # Check behind in target lane
        behind_safe = True
        for offset in range(1, 8):  # Look 8 cells behind
            check_row = self.row + offset
            if 0 <= check_row < ROWS and env.grid[check_row][new_col]:
                # Found a vehicle behind in target lane
                other_vehicle = env.grid[check_row][new_col]
                
                # Calculate happiness scores
                my_happiness = self.calculate_happiness(env)
                other_happiness = other_vehicle.calculate_happiness(env)
                
                # If other vehicle is faster than us, they might hit us
                if other_vehicle.speed > self.speed:
                    needed_distance = max(2, 4 * (other_vehicle.speed - self.speed))
                    # If we have lower happiness, we get priority and need less distance
                    if my_happiness < other_happiness:
                        needed_distance = max(1, needed_distance * 0.7)  # 30% reduction in needed distance
                    if offset < needed_distance:
                        behind_safe = False
                break
                
        # Check for faults in target lane
        fault_distance = float('inf')
        for offset in range(1, FAULT_DETECTION_DISTANCE):
            check_row = self.row - offset
            if 0 <= check_row < ROWS and env.faults[check_row][new_col]:
                fault_distance = offset
                break
                
        # Return True if no immediate faults or if fault is further than current lane
        current_fault = self.detect_faults_ahead(env)
        
        # Evaluate overall safety
        if not ahead_safe or not behind_safe:
            return False
            
        if current_fault:
            # If current lane has fault, target lane should be safer
            if fault_distance > current_fault['distance']:
                return True
            else:
                return False
        elif fault_distance > 3:  # Only change if fault is not too close
            return True
            
        return False

    def plan_lane_change(self, env, fault_info):
        if self.lane_change_cooldown > 0:
            return  # Skip if still cooling down

        if self.is_changing_lane or self.planned_lane_change:
            return  # Already changing or planning
            
        # Try to find a better lane
        left_col = self.col - 1
        right_col = self.col + 1
        
        # Evaluate both directions
        left_safe = self.evaluate_lane_safety(env, left_col) if left_col >= 0 else False
        right_safe = self.evaluate_lane_safety(env, right_col) if right_col < COLS else False
        
        # Choose direction based on safety
        if left_safe and right_safe:
            # Prefer the lane with less traffic ahead
            left_traffic = self.count_traffic_ahead(env, left_col)
            right_traffic = self.count_traffic_ahead(env, right_col)
            if left_traffic <= right_traffic:
                self.planned_lane_change = left_col
            else:
                self.planned_lane_change = right_col
        elif left_safe:
            self.planned_lane_change = left_col
        elif right_safe:
            self.planned_lane_change = right_col
        
        # Set reaction state
        if self.planned_lane_change is not None:
            self.reacting_to_fault = fault_info['type']
            self.reaction_time = 40  # Increased frames to show reaction indicator

    def count_traffic_ahead(self, env, col):
        count = 0
        for offset in range(1, 10):  # Look 10 cells ahead
            check_row = self.row - offset
            if 0 <= check_row < ROWS and env.grid[check_row][col]:
                count += 1
        return count

    def update(self, env, animation_step=False):
        # If we're in animation mode, just update visuals
        if animation_step:
            self.update_animation()
            return
        
        if self.lane_change_cooldown > 0:
            self.lane_change_cooldown -= 1
            
        # Apply weather effects
        original_speed = self.speed
        if env.is_raining:
            # Rain slows down all vehicles
            self.speed *= 0.8
            
            # Random chance of slip during rain
            if random.random() < 0.05:  # Small chance of slipping in rain
                self.yaw = random.uniform(-10, 10)  # Temporary yaw change
        
        # Detect faults ahead
        fault_ahead = self.detect_faults_ahead(env)
        
        # React to faults
        if fault_ahead and not self.is_changing_lane and not self.planned_lane_change:
            # Try to avoid the fault by changing lanes
            self.plan_lane_change(env, fault_ahead)
            
            # If can't change lanes, apply direct effects
            if fault_ahead['type'] == 'pothole' and not self.planned_lane_change:
                # Temporary speed reduction when hitting pothole
                self.speed *= 0.7
        
        # Execute planned lane change if it's time
        if self.planned_lane_change is not None and not self.is_changing_lane:
            # Check again if it's safe
            if self.evaluate_lane_safety(env, self.planned_lane_change):
                # Start lane change animation
                env.grid[self.row][self.col] = None
                self.target_col = self.planned_lane_change
                self.is_changing_lane = True
                env.add_log_message(f"Vehicle {self.id} initiated lane change from lane {self.col} to {self.planned_lane_change}")
                self.animation_progress = 0
                env.grid[self.row][self.target_col] = self
            self.planned_lane_change = None
        
        # Regular forward movement if not changing lanes
        if not self.is_changing_lane:
            # Check for vehicles ahead
            vehicle_ahead = False
            for offset in range(1, SAFE_DISTANCE + 1):
                check_row = self.row - offset
                if check_row >= 0 and env.grid[check_row][self.col]:
                    vehicle_ahead = True
                    break
            
            required_gap = int(self.speed * 1.5)
            for offset in range(1, required_gap + 1):
                check_row = self.row - offset
                if check_row >= 0:
                    other = env.grid[check_row][self.col]
                    if other and other.speed < self.speed - 0.5:
                        if not self.is_changing_lane and not self.planned_lane_change:
                            fault_stub = {'type': 'slow_car', 'distance': offset}
                            env.add_log_message(f"Vehicle {self.id} plans to merge due to slower vehicle at row {check_row}")
                            self.plan_lane_change(env, fault_stub)
                        break

            if not vehicle_ahead:
                next_row = self.row - 1
                if next_row >= 0 and env.grid[next_row][self.col] is None:
                    env.grid[self.row][self.col] = None
                    self.row = next_row
                    self.target_row = next_row
                    self.animation_progress = 0
                    env.grid[self.row][self.col] = self

        self.speed = original_speed
        if self.reaction_time > 0:
            self.reaction_time -= 1
            if self.reaction_time == 0:
                self.reacting_to_fault = None

    def update_animation(self):
        if self.animation_progress < 1.0:
            self.animation_progress += 1.0 / ANIMATION_STEPS
            if self.animation_progress > 1.0:
                self.animation_progress = 1.0

            ease_factor = math.sin(self.animation_progress * math.pi / 2)

            # FIXED SMOOTH MOVEMENT BASED ON START/END POINTS
            start_row = self.row
            start_col = self.col
            end_row = self.target_row
            end_col = self.target_col
            self.visual_row = start_row + (end_row - start_row) * ease_factor
            self.visual_col = start_col + (end_col - start_col) * ease_factor

            if self.animation_progress == 1.0 and self.is_changing_lane:
                self.is_changing_lane = False
                self.col = self.target_col
                self.row = self.target_row
                self.lane_change_cooldown = config["LANE_CHANGE_COOLDOWN"]  # or whatever cooldown value you want


    def draw(self, ego=False):
        # Calculate screen position based on visual coordinates
        x = self.visual_col * CELL_SIZE + LEFT_MARGIN
        y = self.visual_row * CELL_SIZE - camera_offset
        
        if 0 <= y < HEIGHT:
            # Use the appropriate image based on whether this is the ego vehicle
            img = ego_car_img if ego else car_img
            screen.blit(img, (x + 5, y + 5))
            
            # Draw ID text
            font = pygame.font.SysFont(None, 20)
            id_text = font.render(str(self.id), True, (255, 255, 255))
            screen.blit(id_text, (x + CELL_SIZE//2 - 5, y + CELL_SIZE//2 - 5))
            
            # Draw vehicle speed indicator (faster = longer line)
            speed_length = int(self.speed * 10)
            pygame.draw.line(screen, (0, 255, 0), 
                            (x + CELL_SIZE//2, y + CELL_SIZE - 5),
                            (x + CELL_SIZE//2, y + CELL_SIZE - 5 - speed_length), 
                            3)
            
            # Draw fault reaction indicator if active
            if self.reacting_to_fault:
                # Get color based on fault type
                color = FAULTS.get(self.reacting_to_fault, (255, 0, 0))  # Default to red

                # Draw alert icon with pulsing effect
                pulse = abs(math.sin(pygame.time.get_ticks() / 400)) * 0.5 + 0.5  # Slower pulse
                scaled_alert = pygame.transform.scale(
                    alert_img, 
                    (int(25 + 10 * pulse), int(25 + 10 * pulse))  # Larger alert icon
                )
                screen.blit(scaled_alert, (x + CELL_SIZE - 20, y - 5))
                
                # Draw text indicating what fault is being avoided
                font = pygame.font.SysFont(None, 18)
                reaction_text = f"Avoiding {self.reacting_to_fault}"
                text_surface = font.render(reaction_text, True, color)
                screen.blit(text_surface, (x - 20, y - 20))

    def calculate_happiness(self, env):
        # Safety component: based on distance to nearest obstacles
        safety_score = self.calculate_safety_score(env)
        
        # Efficiency component: based on current speed and obstacles ahead
        efficiency_score = self.calculate_efficiency_score(env)
        
        # Comfort component: based on acceleration and yaw changes
        comfort_score = self.calculate_comfort_score()
        
        # Calculate weighted happiness score
        happiness = (
            safety_score * config["SAFETY_WEIGHT"] +
            efficiency_score * config["EFFICIENCY_WEIGHT"] +
            comfort_score * config["COMFORT_WEIGHT"]
        )
        
        # Add to history
        self.happiness_history.append(happiness)
        if len(self.happiness_history) > 10:
            self.happiness_history.pop(0)
        
        return happiness
    
    def calculate_safety_score(self, env):
        # Distance to nearest obstacle (vehicle or fault)
        min_distance = float('inf')
        
        # Check for vehicles ahead
        for offset in range(1, 10):  # Look up to 10 cells ahead
            check_row = self.row - offset
            if check_row >= 0:
                # Check for vehicles in same lane
                if env.grid[check_row][self.col] is not None:
                    min_distance = min(min_distance, offset)
                    break
        
        # Check for faults ahead
        for offset in range(1, 10):
            check_row = self.row - offset
            if check_row >= 0:
                if env.faults[check_row][self.col] is not None:
                    min_distance = min(min_distance, offset)
                    break
        
        # Higher score for greater distance (safer)
        if min_distance == float('inf'):
            return 10.0  # Maximum safety if no obstacles
        else:
            return min(10.0, max(0.0, min_distance / 2.0))
    
    def calculate_efficiency_score(self, env):
        # Based on current speed and clear path ahead
        clear_path_length = 0
        for offset in range(1, 20):  # Look up to 20 cells ahead
            check_row = self.row - offset
            if check_row < 0 or env.grid[check_row][self.col] is not None or env.faults[check_row][self.col] is not None:
                break
            clear_path_length += 1
        
        # Efficiency is higher with higher speed and clear path
        return min(10.0, (self.speed / 3.0) * 5.0 + (clear_path_length / 20.0) * 5.0)
    
    def calculate_comfort_score(self):
        # Lower acceleration and yaw changes mean more comfort
        acceleration_factor = 10.0 - (abs(self.acceleration) * 5.0)
        yaw_factor = 10.0 - (abs(self.yaw) * 1.0)
        
        return min(10.0, max(0.0, (acceleration_factor + yaw_factor) / 2.0))
    

# ----------------------------
# Environment Class
# ----------------------------
class Environment:
    def __init__(self):
        self.vehicles = []
        self.grid = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.faults = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.is_raining = False
        self.rain_frames_left = 0
        self.spawn_vehicles()
        self.updates_per_logic_update = ANIMATION_STEPS
        self.log_messages = []

    def add_log_message(self, message):
        timestamp = time.strftime("%H:%M:%S")
        full_message = f"[{timestamp}] {message}"
        self.log_messages.append(full_message)
        # No trimming, so logs grow until the program ends


    def spawn_vehicles(self):
        initial_rows = []
        for col in range(COLS):
            row = ROWS - 1 - random.randint(0, config["MAX_VEHICLE_DISTANCE"])
            initial_rows.append(row)
        next_id = 0
        for i in range(min(NUM_CARS_SPAWN, len(initial_rows))):
            col = i % COLS
            row = initial_rows[i]
            if self.grid[row][col] is not None:
                continue
            v = Vehicle(row, col, next_id)
            next_id += 1
            self.vehicles.append(v)
            self.grid[v.row][v.col] = v
            v.visual_row = float(row)
            v.visual_col = float(col)

    def try_spawn_new_vehicles(self):
        return  # Dynamic spawning disabled

    def generate_faults_ahead(self):
        # Weather system - chance for rain to start or stop
        if not self.is_raining and random.randint(1, 100) <= int(config["WEATHER_CHANGE_CHANCE"]):
            # Start raining
            self.is_raining = True
            self.rain_frames_left = int(config["RAIN_DURATION"])
            print("It started raining!")
            self.add_log_message("Rain started")
        
        # Count down rain duration
        if self.is_raining:
            self.rain_frames_left -= 1
            if self.rain_frames_left <= 0:
                self.is_raining = False
                print("The rain stopped.")
                self.add_log_message("Rain stopped")
        
        # Fault generation variables
        max_new_faults = 1  # At most one new fault per update
        faults_created = 0
        
        # Calculate actual pothole chance (keep it low)
        actual_pothole_chance = int(config["POTHOLE_CHANCE"]) / 3
        
        # Iterate through vehicles
        for v in self.vehicles:
            # Check if we've reached max faults limit
            if faults_created >= max_new_faults:
                break
                
            # Find the foremost vehicle position
            min_row = min([vehicle.row for vehicle in self.vehicles]) if self.vehicles else 0
            
            # Calculate fault placement position
            fault_distance = random.randint(6, 12)
            fault_row = min(min_row - fault_distance, v.row - fault_distance)
            
            # Skip invalid positions
            if fault_row < 0 or self.faults[fault_row][v.col] is not None:
                continue
                    
            # Initialize fault type
            fault_type = None
            
            # Check for rain fault - only during rain
            if self.is_raining and random.randint(1, 100) <= 30:
                fault_type = 'rain'
            # Check for pothole fault
            elif random.randint(1, 100) <= actual_pothole_chance:
                fault_type = 'pothole'
                
                # Create a pothole
                self.faults[fault_row][v.col] = 'pothole'
                self.add_log_message(f"Pothole created at ({fault_row}, {v.col})")
                faults_created += 1
                
                # Skip to next vehicle
                continue
                    
            # Create the fault if one was selected
            if fault_type:
                self.faults[fault_row][v.col] = fault_type
                faults_created += 1
                    
                # Add additional rain effects
                if fault_type == 'rain' and self.is_raining:
                    for adjacent_col in range(max(0, v.col-1), min(COLS, v.col+2)):
                        if adjacent_col != v.col and random.randint(1, 100) <= 50:
                            if 0 <= fault_row < ROWS and self.faults[fault_row][adjacent_col] is None:
                                self.faults[fault_row][adjacent_col] = 'rain'
        
        # Clean up old rain faults when it stops raining
        if not self.is_raining:
            for r in range(ROWS):
                for c in range(COLS):
                    if self.faults[r][c] == 'rain':
                        self.faults[r][c] = None
                        
        # Count existing potholes
        pothole_count = sum(1 for r in range(ROWS) for c in range(COLS) 
                        if self.faults[r][c] == 'pothole')
                        
        # Remove excess potholes if needed
        max_potholes = 3
        if pothole_count > max_potholes:
            potholes_to_remove = pothole_count - max_potholes
            removed = 0
            
            # Scan the grid to remove old potholes
            for r in range(ROWS-1, -1, -1):
                for c in range(COLS):
                    if self.faults[r][c] == 'pothole' and removed < potholes_to_remove:
                        self.faults[r][c] = None
                        removed += 1
                        
                    if removed >= potholes_to_remove:
                        break

    def evaluate_ego(self):
        # Calculate happiness scores for all vehicles
        happiness_scores = []
        for v in self.vehicles:
            happiness = v.calculate_happiness(self)
            happiness_scores.append((happiness, v))
        
        # Sort by happiness score (higher is better)
        happiness_scores.sort(key=lambda x: -x[0])
        
        # If there are any vehicles, return the one with highest happiness
        if happiness_scores:
            return happiness_scores[0][1]
        else:
            return None

    def update(self, animation_step=False):
        # For animation steps, just update visuals
        if animation_step:
            for v in self.vehicles:
                v.update(self, animation_step=True)
            return
                
        # Try spawning new vehicles
        self.try_spawn_new_vehicles()
        
        # Remove vehicles that have moved off the grid
        for v in self.vehicles[:]:
            if v.row < 0 or v.visual_row < -1:
                if self.grid[v.row][v.col] == v:
                    self.grid[v.row][v.col] = None
                self.add_log_message(f"Vehicle {v.id} exited the simulation")
                self.vehicles.remove(v)

        
        # Update vehicle positions (in order from back to front to avoid conflicts)
        for v in sorted(self.vehicles, key=lambda car: -car.row):
            v.update(self, animation_step=False)

    def draw(self, ego_vehicle):
        screen.fill((30, 30, 30))
        pygame.draw.rect(screen, (50, 50, 50), (0, HEIGHT - 40, WIDTH, 40))
        font = pygame.font.SysFont(None, 20)

        weather_text = "Weather: " + ("Raining (Slippery)" if self.is_raining else "Clear")
        text_surface = font.render(weather_text, True, (200, 200, 200))
        screen.blit(text_surface, (10, HEIGHT - 25))


        for c in range(1, COLS):
            x = c * CELL_SIZE + LEFT_MARGIN
            for y in range(0, HEIGHT - 40, 40):
                pygame.draw.line(screen, (150, 150, 150), (x, y), (x, y + 20), 2)
        # Draw persistent faults
        for r in range(ROWS):
            for c in range(COLS):
                y = r * CELL_SIZE - camera_offset
                if y + CELL_SIZE < 0 or y > HEIGHT:
                    continue
                if self.faults[r][c]:
                    x = c * CELL_SIZE + LEFT_MARGIN
                    fault_type = self.faults[r][c]
                    
                    # Draw different fault visuals based on type
                    if fault_type == 'pothole':
                        # Draw pothole shape
                        pothole_color = FAULTS[fault_type]
                        # Draw main pothole shape
                        pygame.draw.ellipse(screen, pothole_color,
                                        (x + 10, y + 10, CELL_SIZE - 20, CELL_SIZE - 20))
                        # Add dark rim
                        pygame.draw.ellipse(screen, (30, 30, 30),
                                        (x + 15, y + 15, CELL_SIZE - 30, CELL_SIZE - 30))
                        # Add random crack-like pattern
                        for _ in range(4):
                            crack_start = (x + random.randint(5, CELL_SIZE-5), 
                                        y + random.randint(5, CELL_SIZE-5))
                            crack_end = (x + random.randint(5, CELL_SIZE-5), 
                                        y + random.randint(5, CELL_SIZE-5))
                            pygame.draw.line(screen, pothole_color, crack_start, crack_end, 2)
                    elif fault_type == 'rain':
                        # Draw rain puddle
                        rain_color = FAULTS[fault_type]
                        # Draw puddle with ripple effect
                        for i in range(3):
                            radius = (CELL_SIZE - 20) // 2 - i * 3
                            alpha = 180 - i * 40  # Decreasing alpha for outer ripples
                            s = pygame.Surface((radius*2, radius*2), pygame.SRCALPHA)
                            pygame.draw.ellipse(s, (rain_color[0], rain_color[1], rain_color[2], alpha), 
                                            (0, 0, radius*2, radius*2))
                            screen.blit(s, (x + CELL_SIZE//2 - radius, y + CELL_SIZE//2 - radius))
                    
                    # Add a small icon/label to indicate fault type
                    font = pygame.font.SysFont(None, 16)
                    
                    # First letter of fault type
                    icon_text = fault_type[0].upper()
                    text_surface = font.render(icon_text, True, (0, 0, 0))
                    screen.blit(text_surface, (x + CELL_SIZE//2 - 4, y + CELL_SIZE//2 - 4))

        # Draw vehicles
        for v in self.vehicles:
            v.draw(ego=(v == ego_vehicle))
        # Draw rain effect if it's raining
        if self.is_raining:
            for _ in range(40):  # Draw multiple raindrops
                rain_x = random.randint(0, WIDTH)
                rain_y = random.randint(0, HEIGHT - 40)  # Don't draw over dashboard
                rain_length = random.randint(5, 15)
                pygame.draw.line(screen, (200, 200, 255), 
                                (rain_x, rain_y), 
                                (rain_x - 2, rain_y + rain_length), 
                                1)
        # --- Draw Axis Labels ---
        axis_font = pygame.font.SysFont(None, 16)

        # Draw Y-axis (row numbers)
        for r in range(0, ROWS):
            y = r * CELL_SIZE - camera_offset
            if 0 <= y < HEIGHT - 40:  # Avoid drawing over dashboard
                label = axis_font.render(f"R{r}", True, (200, 200, 200))
                screen.blit(label, (5, y + 2))  # Offset left for visibility

        # Draw X-axis (column headers)
        for c in range(COLS):
            x = c * CELL_SIZE + LEFT_MARGIN
            label_text = f"C{c}"
            label = axis_font.render(label_text, True, (200, 200, 200))
            label_width = label.get_width()
            screen.blit(label, (x + CELL_SIZE // 2 - label_width // 2, HEIGHT - 35))

        # --- Draw Log Panel ---
        log_panel_x = LEFT_MARGIN + COLS * CELL_SIZE + 10  # Leave gap after last column
        log_panel_y = 10
        log_panel_width = 190  # Width inside the RIGHT_MARGIN

        # Draw background for log panel
        pygame.draw.rect(screen, (20, 20, 20), (LEFT_MARGIN + COLS * CELL_SIZE, 0, RIGHT_MARGIN, HEIGHT - 40))

        # Draw log messages
        log_font = pygame.font.SysFont(None, 18)
        for log in self.log_messages[-20:]:  # Show last 20 entries
            log_surface = log_font.render(log, True, (255, 255, 255))
            screen.blit(log_surface, (log_panel_x + 10, log_panel_y))
            log_panel_y += 20

        pygame.display.flip()

# ----------------------------
# Main Loop
# ----------------------------
def main():
    global camera_offset
    env = Environment()
    history = []
    running = True
    paused = False
    animation_step = 0
    camera_offset = 0

    while running:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    paused = not paused
                elif event.key == pygame.K_RIGHT and paused:
                    snapshot = copy.deepcopy(env)
                    history.append(snapshot)
                    env.generate_faults_ahead()
                    ego_vehicle = env.evaluate_ego()
                    env.update(animation_step=False)
                    if ego_vehicle:
                        camera_offset = max(0, ego_vehicle.row * CELL_SIZE - HEIGHT // 2)
                    animation_step = 0
                elif event.key == pygame.K_LEFT and paused and history:
                    env = history.pop()
                    animation_step = 0

        if not paused:
            if animation_step == 0:
                snapshot = copy.deepcopy(env)
                history.append(snapshot)
                env.generate_faults_ahead()
                ego_vehicle = env.evaluate_ego()
                env.update(animation_step=False)
                if ego_vehicle:
                    camera_offset = max(0, ego_vehicle.row * CELL_SIZE - HEIGHT // 2)

            env.update(animation_step=True)
            animation_step = (animation_step + 1) % ANIMATION_STEPS

        env.draw(env.evaluate_ego())

    pygame.quit()

if __name__ == "__main__":
    main()