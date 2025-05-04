        for c in range(COLS):
            x = c * CELL_SIZE + LEFT_MARGIN
            label_text = f"C{c}"
            label = axis_font.render(label_text, True, (200, 200, 200))
            label_width = label.get_width()
            screen.blit(label, (x + CELL_SIZE // 2 - label_width // 2, HEIGHT - 35))