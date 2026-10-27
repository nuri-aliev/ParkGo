import tkinter as tk
import random

# ---------- SETTINGS ----------
WIDTH = 920
HEIGHT = 600
BG = "#08090b"
PANEL = "#17181b"
WHITE = "#f4f7f3"
MINT = "#b9f3dc"
GREEN = "#a8e77e"
GRAY = "#92999a"

root = tk.Tk()
root.title("float")
root.geometry(f"{WIDTH}x{HEIGHT}")
root.configure(bg=BG)
root.minsize(720, 460)

# ---------- HEADER ----------
header = tk.Frame(root, bg=PANEL)
header.pack(fill="x")

title = tk.Label(
    header,
    text="float",
    bg=PANEL,
    fg="#eeeeee",
    font=("Ubuntu", 11, "bold"),
    pady=10
)
title.pack()

# ---------- MAIN AREA ----------
main = tk.Frame(root, bg=BG)
main.pack(fill="both", expand=True, padx=20, pady=12)

main.grid_columnconfigure(0, weight=3)
main.grid_columnconfigure(1, weight=2)
main.grid_rowconfigure(0, weight=1)

# ---------- PIXEL ART ----------
art = tk.Canvas(
    main,
    bg=BG,
    highlightthickness=0
)
art.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

# Pixel-art character. Each character is one pixel.
sprite = [
    "      WWWW             WWWW       ",
    "     WWWWWW           WWWWWW      ",
    "    WWWWWWWW         WWWWWWWW     ",
    "   WWWWWWWWW         WWWWWWWWW    ",
    "   WWWWWWWWWWW     WWWWWWWWWWW    ",
    "    WWWWWWWWWWWWWWWWWWWWWWWWW     ",
    "     WWWWWWWWWWWWWWWWWWWWWWW      ",
    "      WWWWWWWWWWWWWWWWWWWWW       ",
    "   GGGWWWWWWWWWWWWWWWWWWWWWGGG    ",
    "  GGGGGWWWWWWWWWWWWWWWWWWWWWGGGG   ",
    " GGGGGGWWWWWWWWWWWWWWWWWWWWWGGGGG  ",
    " GGGGMMWWWWWWWWWWWWWWWWWWWWWMMGGGG ",
    " GGGGMMMWWWWWWWWWWWWWWWWWWWMMM GGG ",
    "  GGGGMMMMWWWWWWWWWWWWWWWMMMMGGGG   ",
    "   GGGGMMMMMWWWWWWWWWWWMMMMMGGGG    ",
    "    GGGMMMMMMWWWWWWWWWMMMMMMGGG     ",
    "     GGGMMMMMMWWWWWWWMMMMMMGGG      ",
    "      GGGMMMMMWWWWWWWMMMMMGGG       ",
    "       GGGGMMMMWWWWWMMMMGGGG        ",
    "        GGGGMMMMWWWWWMMMMGGG        ",
    "         GGGGMMMMWWWWWMMMMGG         ",
    "          GGGMMMMWWWWWMMMMGG         ",
    "           GGGMMMMWWWWWMMMG           ",
    "            GGGMMMMWWWMMMG            ",
    "             GGGMMMMWMMMG             ",
    "              GGGGMMMMGG              ",
    "               GGGGGGGG               ",
]

colors = {
    "W": "#f4f7f3",
    "M": "#b7efd9",
    "G": "#a7e47b",
}

def draw_sprite(event=None):
    art.delete("sprite")

    cell = min(
        (art.winfo_width() - 30) / 37,
        (art.winfo_height() - 50) / len(sprite)
    )
    cell = max(5, min(cell, 20))

    sprite_width = max(map(len, sprite)) * cell
    sprite_height = len(sprite) * cell

    start_x = max(12, (art.winfo_width() - sprite_width) / 2)
    start_y = max(12, (art.winfo_height() - sprite_height) / 2)

    for row, line in enumerate(sprite):
        for col, pixel in enumerate(line):
            if pixel in colors:
                x = start_x + col * cell
                y = start_y + row * cell

                art.create_rectangle(
                    x, y, x + cell + 0.4, y + cell + 0.4,
                    fill=colors[pixel],
                    outline=colors[pixel],
                    tags="sprite"
                )

art.bind("<Configure>", draw_sprite)

# ---------- RIGHT PANEL ----------
side = tk.Frame(main, bg=BG)
side.grid(row=0, column=1, sticky="nsew", padx=(8, 10), pady=15)

def stat_line(symbol, value):
    line = tk.Frame(side, bg=BG)
    line.pack(fill="x", pady=4)

    tk.Label(
        line, text=symbol, fg="#b4f2dc",
        bg=BG, font=("Ubuntu", 15)
    ).pack(side="left", padx=(0, 12))

    tk.Label(
        line, text=value, fg=WHITE,
        bg=BG, font=("Ubuntu Mono", 12, "bold")
    ).pack(side="left")

stat_line("➜", "1.66 GiB / 15.36 GiB")
stat_line("◷", "35 mins")
stat_line("⌛", "3 days")

# ---------- SLIDER ----------
slider_value = tk.DoubleVar(value=50)

slider = tk.Scale(
    side,
from_=0,
    to=100,
    orient="horizontal",
    variable=slider_value,
    bg=BG,
    fg=GRAY,
    troughcolor="#34363a",
    activebackground="#d7e4e1",
    highlightthickness=0,
    bd=0,
    showvalue=False,
    sliderlength=14,
    command=lambda value: None
)
slider.pack(fill="x", pady=(10, 20))

# ---------- COLOR DOTS ----------
colors_list = [
    "#f18bbd", "#85e8d2", "#f0d16a", "#8589ff",
    "#b6a1ff", "#81d5ed", "#c6cbd0", "#4a4d55"
]

selected_color = tk.StringVar(value=colors_list[0])

dots = tk.Frame(side, bg=BG)
dots.pack(fill="x", pady=4)

def select_color(color):
    selected_color.set(color)
    for widget in dots.winfo_children():
        widget.configure(
            highlightbackground=(
                "#ffffff" if widget.color_value == color else BG
            ),
            highlightthickness=(
                2 if widget.color_value == color else 0
            )
        )

for color in colors_list:
    dot = tk.Canvas(
        dots, width=18, height=18,
        bg=BG, highlightthickness=0,
        cursor="hand2"
    )
    dot.pack(side="left", expand=True)

    dot.create_oval(4, 4, 14, 14, fill=color, outline=color)
    dot.color_value = color
    dot.bind("<Button-1>", lambda event, c=color: select_color(c))

select_color(colors_list[0])

# ---------- FOOTER ----------
footer = tk.Frame(root, bg=PANEL, height=30)
footer.pack(fill="x", side="bottom")

tk.Label(
    footer,
    text="FLOAT  •  DESKTOP WIDGET",
    bg=PANEL,
    fg="#777e84",
    font=("Ubuntu", 8),
    pady=7
).pack()

# Redraw sprite after the window appears
root.after(100, draw_sprite)

root.mainloop()
