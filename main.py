"""Entry point. Keep this file thin — all real code lives in app/."""

from app.gui.app import App


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
