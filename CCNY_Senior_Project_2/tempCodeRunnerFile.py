    def spawn_vehicles(self):
        for col in range(COLS):
            v = Vehicle(ROWS - 1, col, col)
            self.vehicles.append(v)
            self.grid[v.row][v.col] = v