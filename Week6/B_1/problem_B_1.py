
def generateCSV(KB):
    pass

class DataFrameProcessor:
    def __init__(self):
        pass

    def read_csv(self):
        pass



if __name__ == "__main__":
    df_reader = DataFrameProcessor()
    KB=64
    while True:
        try:
            print(f"Generating {KB} KB CSV...")
            generateCSV(KB)
            print(f"Reading {KB} KB CSV...")
            df = df_reader.read_csv()
            print(f"KB {KB}: Success - Sums: {df.head()}")
        except MemoryError:
            print(f"KB {KB}: Failed with MemoryError")
            break
        except Exception as e:
            print(f"KB {KB}: Failed with {type(e).__name__}: {e}")
            break
        KB*=2
