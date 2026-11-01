"""Explicit offline generation; never runs in ordinary application startup."""

from scripts.dataset_v2.generate import generate

if __name__ == "__main__":
    print(generate())
