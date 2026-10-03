import csv
import os
import shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SOURCE_FILE = os.path.join(BASE_DIR, "alerts.csv")
TEMP_FILE = os.path.join(BASE_DIR, "alerts_migrated.csv")

COLUMNS = [
    "Timestamp",
    "Symbol",
    "OldState",
    "NewState",
    "Price",
    "RVOL",
    "Continuation",
    "RadarScore",
    "GainPercent",
    "IgnitionReason",
]


def migrate_alerts():

    migrated = 0
    legacy = 0
    current = 0
    skipped = 0

    with open(
        SOURCE_FILE,
        "r",
        newline="",
        encoding="utf-8-sig"
    ) as source:

        reader = csv.reader(source)

        # Remove existing historical header
        old_header = next(reader, None)

        print("OLD HEADER:")
        print(old_header)
        print()

        with open(
            TEMP_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as destination:

            writer = csv.writer(destination)

            # Write the current 10-column schema
            writer.writerow(COLUMNS)

            for line_number, row in enumerate(
                reader,
                start=2
            ):

                if not row:
                    continue

                if len(row) == 9:

                    # Legacy record:
                    # add blank IgnitionReason
                    row.append("")

                    legacy += 1

                elif len(row) == 10:

                    current += 1

                else:

                    print(
                        f"SKIPPED line {line_number}: "
                        f"{len(row)} fields -> {row}"
                    )

                    skipped += 1
                    continue

                writer.writerow(row)

                migrated += 1

    print()
    print("==============================")
    print("ALERT MIGRATION COMPLETE")
    print("==============================")
    print(f"Total migrated: {migrated}")
    print(f"Legacy 9-field rows: {legacy}")
    print(f"Current 10-field rows: {current}")
    print(f"Skipped malformed rows: {skipped}")
    print()

    if skipped > 0:

        print(
            "Migration created alerts_migrated.csv, "
            "but alerts.csv was NOT replaced because "
            "malformed records were found."
        )

        return

    # Everything validated successfully.
    shutil.move(
        TEMP_FILE,
        SOURCE_FILE
    )

    print(
        "alerts.csv successfully replaced "
        "with normalized 10-column version."
    )


if __name__ == "__main__":
    migrate_alerts()