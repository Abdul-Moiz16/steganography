from PIL import Image


class SequentialLSB:

    def embed_lsb(self, cover_image: Image.Image, payload_bytes: bytes, fill_rate: float, *,
                  bit_depth: int = 1) -> Image.Image:
        """Embed a payload with sequential grayscale LSB replacement."""

        img = cover_image.convert("L")  # grayscale/ redundant convert but safer
        pixels = list(img.get_flattened_data())
        num_pixels = len(pixels)

        bit_chunks = []
        for byte in payload_bytes:
            bit_chunks.append(f"{byte:08b}")
        bits = "".join(bit_chunks)  # collection of all bits to embed

        usable_pixels = int(num_pixels * fill_rate)  # calculate usable pixels to embed payload
        capacity = usable_pixels * bit_depth  # every pixel can store bit_depth bits

        if len(bits) > capacity:
            raise ValueError(f"too large payload: {len(bits)} bits, but image can only store {capacity}.")

        order = list(range(usable_pixels))  # sequential row-major order
        bit_index = 0

        for pixel_pos in order:

            value = pixels[pixel_pos]  # get current greyscale value

            mask = ~((1 << bit_depth) - 1)
            value = value & mask  # clear last bit_depth bits

            for b in range(bit_depth):  # embed bit_depth bits per pixel

                if bit_index >= len(bits):
                    break  # no more bits left to embed

                bit = int(bits[bit_index])  # get bit to embed

                pos = bit_depth - 1 - b
                shifted_bit = bit << pos

                value |= shifted_bit  # set bit
                bit_index += 1

            pixels[pixel_pos] = value  # update original pixel to modified one

            if bit_index >= len(bits):  # no more bits to embed
                break

        img_out = Image.new("L", img.size)
        img_out.putdata(pixels)
        return img_out

    def decode_lsb(self, stego_image: Image.Image, fill_rate: float, payload_length: int, *, bit_depth: int = 1) -> bytes:
        """Just for Testing/ Verification Purposes"""

        img = stego_image.convert("L")
        pixels = list(img.get_flattened_data())
        num_pixels = len(pixels)

        usable_pixels = int(num_pixels * fill_rate) # same fraction as during embedding
        order = list(range(usable_pixels)) # same sequential order as for embedding

        all_bits = []  # collection of all read bits
        total_bits_needed = payload_length * 8

        for pixel_pos in order: # go through pixels
            value = pixels[pixel_pos] # get grayscale value of selected pixel

            for b in range(bit_depth): # read bit_depth bits per pixel
                bit = (value >> (bit_depth - 1 - b)) & 1  # read bit
                all_bits.append(str(bit)) # add bit to collection

            if len(all_bits) >= total_bits_needed: # enough bits read
                break

        all_bits = all_bits[:total_bits_needed] # trim excess bits

        # convert bit stream to bytes
        byte_list = []
        for i in range(0, len(all_bits), 8):
            chunk = all_bits[i:i + 8]
            if len(chunk) < 8: # check for incomplete bytes at the end
                break
            number = int("".join(chunk), 2) # take chunk (8 bits) and convert to int
            byte_list.append(number) # append number to list

        return bytes(byte_list)
