import tkinter as tk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure


class ChartPanel:

    def __init__(self, parent):

        self.figure = Figure(figsize=(8, 5), dpi=100)

        self.ax = self.figure.add_subplot(111)

        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=parent
        )

        self.canvas.get_tk_widget().pack(
            fill="both",
            expand=True
        )

    def clear(self):

        self.ax.clear()

    def plot_symbol(
            self,
            symbol,
            df
    ):

        self.ax.clear()

        self.ax.plot(
            df.index,
            df["c"],
            label="Price"
        )

        if "VWAP" in df.columns:

            self.ax.plot(
                df.index,
                df["VWAP"],
                label="VWAP"
            )

        self.ax.set_title(symbol)

        self.ax.legend()

        self.canvas.draw()