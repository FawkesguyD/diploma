from __future__ import annotations

from model.ml.model.main import parse_args, run_from_args, run_pipeline


if __name__ == "__main__":
    args = parse_args()
    run_from_args(args)
