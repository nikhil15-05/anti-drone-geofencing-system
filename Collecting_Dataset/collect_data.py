import serial
import csv
import sys
import os
from datetime import datetime

SERIAL_PORT = os.getenv('SERIAL_PORT')
BAUD_RATE = 115200

# Store recordings where the training script discovers them.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'Models_and_Dataset', 'Datasets'))
os.makedirs(DATASET_DIR, exist_ok=True)

# Define separate CSV file paths for each class
FILE_PREFIXES = {
    0: 'class_0_ambient',
    1: 'class_1_target_rf_source',
    2: 'class_0_wifi_stress'
}

def new_session_path(label):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(DATASET_DIR, f'{FILE_PREFIXES[label]}_{timestamp}.csv')

def collect_samples(label_name, num_samples, output_file):
    if not SERIAL_PORT:
        print("[-] Set the SERIAL_PORT environment variable to the device's serial port.")
        return

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"\n[+] Connected to {SERIAL_PORT}")
        print(f"[+] Recording {num_samples} frames for Class '{label_name}'...")
        print(f"[+] Target File: {os.path.basename(output_file)}")
        print("[+] Press Ctrl+C at any time to stop early.\n")
    except Exception as e:
        print(f"[-] Failed to open serial port {SERIAL_PORT}: {e}")
        return

    samples_saved = 0

    try:
        # Open CSV in append mode
        with open(output_file, mode='a', newline='') as f:
            writer = csv.writer(f)

            # Write header if file is brand new/empty
            if f.tell() == 0:
                header = [f'ch_{i}' for i in range(125)] + ['label']
                writer.writerow(header)

            while samples_saved < num_samples:
                line = ser.readline().decode('utf-8', errors='ignore').strip()

                # Validate full 125-character binary frame
                if len(line) == 125 and all(c in '01' for c in line):
                    frame = [int(bit) for bit in line]
                    frame.append(label_name)
                    writer.writerow(frame)
                    samples_saved += 1

                    if samples_saved % 250 == 0:
                        print(f"Progress: {samples_saved}/{num_samples} frames collected...")

        print(f"\n[SUCCESS] Added {samples_saved} frames to {os.path.basename(output_file)}!\n")

    except KeyboardInterrupt:
        print(f"\n[!] Stopped early. Saved {samples_saved} frames to {os.path.basename(output_file)}.\n")
    finally:
        ser.close()

def main():
    while True:
        print("=" * 55)
        print("        RF DATASET COLLECTION MENU")
        print("=" * 55)
        print("  [1] Record Ambient Background / Quiet -> class_0_ambient.csv")
        print("  [2] Record Target RF Source Active  -> class_1_target_rf_source.csv")
        print("  [3] Record Heavy Wi-Fi Stress       -> class_2_wifi_stress.csv")
        print("  [4] Custom Recording (Specify label & filename)")
        print("  [5] Exit")
        print("=" * 55)

        choice = input("Select an option (1-5): ").strip()

        if choice == '1':
            input("\nEnsure the target transmitter is off. Press ENTER to start...")
            collect_samples(label_name=0, num_samples=3000, output_file=new_session_path(0))

        elif choice == '2':
            input("\nTurn ON the target transmitter (currently the 2.4 GHz RC car/controller). Press ENTER to start...")
            collect_samples(label_name=1, num_samples=3000, output_file=new_session_path(1))

        elif choice == '3':
            input("\nStart a heavy Wi-Fi Speed Test / 4K stream. Press ENTER to start...")
            collect_samples(label_name=0, num_samples=3000, output_file=new_session_path(2))

        elif choice == '4':
            try:
                label = int(input("Enter label (0 = background/non-target, 1 = target RF source): ").strip())
                count = int(input("Enter number of samples to collect (e.g. 1000): ").strip())
                fname = input("Enter custom CSV filename (e.g. class_1_target_room2.csv): ").strip()
                custom_path = os.path.join(DATASET_DIR, fname)
                
                input(f"Ready to record {count} samples. Press ENTER to start...")
                collect_samples(label_name=label, num_samples=count, output_file=custom_path)
            except ValueError:
                print("\n[-] Invalid input. Please enter valid numbers.\n")

        elif choice == '5':
            print("\nExiting data collector. Happy training!\n")
            sys.exit(0)

        else:
            print("\n[-] Invalid selection. Please choose an option between 1 and 5.\n")

if __name__ == '__main__':
    main()