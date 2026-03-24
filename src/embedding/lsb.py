import hashlib
import random
from PIL import Image


class LSB:
    def __init__(self, key: str):
        self.key = key

    def _get_pixel_order(self, num_pixels: int) -> list[int]:
        """ Generate a deterministic pixel order based on the key. """

        key_bytes = self.key.encode("utf-8")  # convert string to bytes
        hash_object = hashlib.sha256(key_bytes)
        hex_hash = hash_object.hexdigest()  # take hashed bytes and convert to hex
        seed = int(hex_hash, 16)  # take hex and convert to int

        indices = list(range(num_pixels))  # number of available pixels in carry

        rng = random.Random(seed)  # deterministic with same seed
        rng.shuffle(indices)

        return indices

    def _message_to_bits(self, message: str) -> str:
        """ Converts a message string into a bit string.
            The first 32 bits is a header storing the number of payload bytes, followed by the actual message bits. """

        data = message.encode("utf-8")  # convert string to bytes
        length = len(data)  # amount of bytes to hide
        length_bytes = length.to_bytes(4, "big")  # 32 bit header to store length of payload
        all_bytes = length_bytes + data  # header + payload in bytes

        bits = ""

        for byte in all_bytes:
            binary = format(byte, "08b")  # convert byte to bits
            bits += binary  # concat

        return bits

    def _bits_to_message(self, bits: str) -> str:
        """ Reads the 32-bit length header first to determine payload size,
            then converts the remaining bits back into bytes and decodes to UTF-8. """

        length = int(bits[:32], 2)  # read header and convert to amount of bytes (int)
        message_bits = bits[32:32 + length * 8]  # get actual message bits

        byte_list = []
        for i in range(0, len(message_bits), 8):  # always take chunks of 8 bits
            bits = message_bits[i:i + 8]  # take one chunk
            number = int(bits, 2)  # take chunk (8 bits) and convert to int
            byte_list.append(number)  # append number to list

        raw_bytes = bytes(byte_list)  # convert list of int to bytes
        message = raw_bytes.decode("utf-8")  # convert bytes to string
        return message

    def encode(self, image_path: str, message: str, output_path: str) -> None:
        """ Hide a message in an image by writing bits into the LSBs of RGB channels.
            Pixel order is key-based. Output must be PNG to preserve the embedded data. """

        img = Image.open(image_path).convert("RGB")
        pixels = list(img.getdata())
        num_pixels = len(pixels)

        bits = self._message_to_bits(message)
        capacity = num_pixels * 3  # on bit per color (r,g,b)
        if len(bits) > capacity:
            raise ValueError(f"too large payload: {len(bits)} bits, but image can only store {capacity}.")

        order = self._get_pixel_order(num_pixels)  # will always be the same for same key
        bit_index = 0

        for pixel_pos in order:
            r, g, b = pixels[pixel_pos]  # get r,g,b values out of carrier
            channels = [r, g, b]

            for c in range(3):  # modify r, then g, then b

                if bit_index >= len(bits):
                    break  # no more bits left to embed

                value = channels[c]
                value = value & ~1  # clear last bit

                bit = int(bits[bit_index])  # get bit to embed
                value = value | bit  # set bit
                channels[c] = value  # update pixel
                bit_index += 1

            new_pixel = (channels[0], channels[1], channels[2])
            pixels[pixel_pos] = new_pixel  # update original pixel to modified one

            if bit_index >= len(bits):  # no more bits to embed
                break

        img_out = Image.new("RGB", img.size)
        img_out.putdata(pixels)
        img_out.save(output_path, "PNG")

    def decode(self, image_path: str) -> str:
        """ Extract a hidden message by reading LSBs in the same key-based pixel order.
            Reads the 32-bit length header first, then the payload bits. """

        img = Image.open(image_path).convert("RGB")
        pixels = list(img.getdata())
        num_pixels = len(pixels)

        order = self._get_pixel_order(num_pixels)  # same order as for encryption since same key

        all_bits = []  # collection of all read bits

        total_bits_needed = 32  # first only header
        header_read = False  # header still needs to be read

        for pixel_pos in order:  # go through pixels
            r, g, b = pixels[pixel_pos]  # get r, g, b values of selected pixel

            for channel in (r, g, b):
                bit = channel & 1  # read last bit
                all_bits.append(str(bit))  # add bit to collection

            if len(all_bits) >= 32 and not header_read:
                header_bits = "".join(all_bits[:32])  # get header in bits
                length = int(header_bits, 2)  # convert bits from header to int

                total_bits_needed = 32 + length * 8  # calculate amount of bits of payload + 32 bits for header
                header_read = True  # flag to not check again

            if len(all_bits) >= total_bits_needed:  # all bits read
                break

        message_bits = "".join(all_bits[:total_bits_needed])
        return self._bits_to_message(message_bits)


'''if __name__ == "__main__":  # for testing purposes :)
    from lsb import LSB

    key = "coolKey"
    stego = LSB(key)

    stego.encode("screenshot.png", "secret message", "output.png")
    print("message hidden")

    msg = stego.decode("output.png")
    print(f"decoded: {msg}")'''
