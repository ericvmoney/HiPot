"""Publish step: join jobs, the company registry and the taxonomy into the one
data file the board page loads (`site/data/board.json`).

    uv run python -m pipeline.publish [--jobs data/seed/jobs.json] [--out site/data/board.json]

See `build.py` for the rules and `board.schema.json` for the shape of the output.
"""
from pipeline.publish.build import (
    BOARD_VERSION, PAY_VERSION, PublishError, build_board, build_pay, dumps_board, dumps_pay, write_board, write_pay,
)

__all__ = ["BOARD_VERSION", "PAY_VERSION", "PublishError", "build_board", "build_pay", "dumps_board", "dumps_pay",
           "write_board", "write_pay"]
