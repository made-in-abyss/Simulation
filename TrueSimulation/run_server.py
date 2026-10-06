"""
Interactive Server Launcher for the Market Simulator.
Runs FastAPI + Uvicorn server serving the Trading Terminal UI at http://127.0.0.1:8000.
"""

import sys
import os
import uvicorn

# Add simulator root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


def main():
    port = 8000
    host = "127.0.0.1"
    print("\n" + "=" * 65)
    print(" REALISTIC FINANCIAL MARKET SIMULATOR - INTERACTIVE TERMINAL")
    print(f" Web Trading Terminal URL: http://{host}:{port}")
    print("=" * 65)
    print(" Press Ctrl+C in terminal to stop the server.\n")

    uvicorn.run("ui.server:app", host=host, port=port, log_level="info", reload=False)


if __name__ == "__main__":
    main()
