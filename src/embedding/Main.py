from PIL import Image


class Main:

    def __init__(self):
        self.input_image_path = "test.png"
        self.fill_rate = 0.50
        self.bit_depth = 1
        self.message = "this is a super secret message"

    def test_sequential(self):
        from SequentialLSB import SequentialLSB

        stego = SequentialLSB()
        img = Image.open(self.input_image_path)
        payload = self.message.encode("utf-8")

        print("--- Sequential LSB ---")
        print(f"Original: {self.message}")

        stego_img = stego.embed_lsb(img, payload, self.fill_rate, bit_depth=self.bit_depth)
        stego_img.save("output_sequential.png")

        stego_img_loaded = Image.open("output_sequential.png")
        decoded = stego.decode_lsb(stego_img_loaded, self.fill_rate, len(payload), bit_depth=self.bit_depth)
        print(f"Decoded:  {decoded.decode('utf-8')}")

    def test_keyed(self):
        from KeyedLSB import KeyedLSB

        stego = KeyedLSB(key="coolKey")
        img = Image.open(self.input_image_path)
        payload = self.message.encode("utf-8")

        print("\n--- Keyed LSB ---")
        print(f"Original: {self.message}")

        stego_img = stego.embed_lsb(img, payload, self.fill_rate, bit_depth=self.bit_depth)
        stego_img.save("output_keyed.png")

        stego_img_loaded = Image.open("output_keyed.png")
        decoded = stego.decode_lsb(stego_img_loaded, self.fill_rate, len(payload), bit_depth=self.bit_depth)
        print(f"Decoded:  {decoded.decode('utf-8')}")

    def run(self):
        self.test_sequential()
        self.test_keyed()


if __name__ == "__main__":
    Main().run()