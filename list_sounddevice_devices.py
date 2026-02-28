#!/usr/bin/env python3
import sounddevice as sd


def main() -> None:
    print("Available audio devices:")
    print(sd.query_devices())
    print("\nDefault device indices (input, output):")
    print(sd.default.device)


if __name__ == "__main__":
    main()
