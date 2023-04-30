"""
This module contains the SpriteScraper class, which is used to download images from the OSRS Wiki.
This utility does not work well with IPv6. If you are having issues, try disabling IPv6 on your machine.
"""

import os
import re
from enum import Enum
from typing import List

import cv2
import numpy as np
import requests

if __name__ == "__main__":
    import sys

    sys.path[0] = os.path.dirname(sys.path[0])

import utilities.imagesearch as imsearch

DEFAULT_DESTINATION = imsearch.BOT_IMAGES.joinpath("scraper")


class ImageType(Enum):
    NORMAL = 0
    BANK = 1
    ALL = 2


class SpriteScraper:
    def __init__(self):
        self.base_url = "https://oldschool.runescape.wiki/"

    def search_and_download(self, search_string: str, **kwargs):
        """
        Searches the OSRS Wiki for the given search parameter and downloads the image(s) to the appropriate folder.
        Args:
            search_string: A comma-separated list of wiki keywords to locate images for.
        Keyword Args:
            image_type: 0 = NORMAL, 1 = BANK, 2 = ALL. Normal sprites are full-size, and bank sprites are cropped at the top
                        to improve image search performance within the bank interface (crops out stack numbers). Default is 0.
            destination: The folder to save the downloaded images to. Default is defined in the global `DEFAULT_DESTINATION`.
            notify_callback: A function (usually defined in the view) that takes a string as a parameter. This function is
                             called with search results and errors. Default is print().
        Example:
            This is an example of using the scraper from a Bot script to download images suitable for searching in the bank:
            >>> scraper = SpriteScraper()
            >>> scraper.search_and_download(
            >>>     search_string = "molten glass, bucket of sand",
            >>>     image_type = ImageType.BANK,
            >>>     destination = imsearch.BOT_IMAGES.joinpath("bank"),
            >>>     notify_callback = self.log_msg,
            >>> )
        """
        image_type = kwargs.get("image_type", ImageType.NORMAL)
        destination = kwargs.get("destination", DEFAULT_DESTINATION)
        notify_callback = kwargs.get("notify_callback", print)

        # Ensure the iamge_type is valid
        if isinstance(image_type, ImageType):
            notify_callback("Invalid image type argument.")
            return

        # Format search args into a list of strings
        img_names = self.format_args(search_string)
        if not img_names:
            notify_callback("No search terms entered.")
            return
        notify_callback("Beginning search...\n")

        # Iterate through each image name and download the image
        i = -1
        while i < len(img_names) - 1:
            i += 1

            # Fix capitalization
            img_names[i] = self.capitalize_each_word(img_names[i])
            notify_callback(f"Searching for {img_names[i]}...")

            # Get image URL
            img_url = self.__sprite_url(img_names[i])
            if img_url is None:
                notify_callback(f"No image found for {img_names[i]}.\n")
                continue
            notify_callback("Found image.")

            # Download image
            notify_callback("Downloading image...")
            try:
                downloaded_img = self.__download_image(img_url)
            except requests.exceptions.RequestException as e:
                notify_callback(f"Network error: {e}\n")
                continue
            except cv2.error as e:
                notify_callback(f"Image decoding error: {e}\n")
                continue

            # Save image according to image_type argument
            filepath = destination.joinpath(img_names[i])
            if image_type in {ImageType.NORMAL, ImageType.ALL}:
                cv2.imwrite(f"{filepath}.png", downloaded_img)
                nl = "\n"
                notify_callback(f"Success: {img_names[i]} sprite saved.{nl if image_type != 2 else ''}")
            if image_type in {ImageType.BANK, ImageType.ALL}:
                cropped_img = self.bankify_image(downloaded_img)
                cv2.imwrite(f"{filepath}_bank.png", cropped_img)
                notify_callback(f"Success: {img_names[i]} bank sprite saved.\n")

        notify_callback(f"Search complete. Images saved to:\n{destination}.\n")

    def bankify_image(self, image: cv2.Mat) -> cv2.Mat:
        """
        Converts a sprite into an image that is suitable for image searching within a bank interface.
        This function centers the image in a 36x32 frame, and deletes some pixels at the top of the image to
        remove the stack number.
        Args:
            image: The image to crop.
        Returns:
            The bankified image.
        """
        height, width = image.shape[:2]
        max_height, max_width = 32, 36

        if height > max_height or width > max_width:
            print("Warning: Image is already larger than bank slot. This sprite is unlikely to be relevant for bank functions.")
            return image

        height_diff = max_height - height
        width_diff = max_width - width
        image = cv2.copyMakeBorder(image, height_diff // 2, height_diff // 2, width_diff // 2, width_diff // 2, cv2.BORDER_CONSTANT, value=0)
        image[:9, :] = 0
        return image

    def capitalize_each_word(self, string: str) -> str:
        """
        Capitalizes the first letter of each word in a string of words separated by underscores, retaining the
        underscores.
        """
        exclude = ["from", "of", "to", "in", "with", "on", "at", "by", "for"]
        return "_".join(word if word in exclude else word.capitalize() for word in string.split("_"))

    def format_args(self, string: str) -> List[str]:
        """
        Formats a comma-separated list of strings into a list of strings where each string is capitalized and
        underscores are used instead of spaces.
        """
        # If the string is empty, return an empty list
        if not string.strip():
            return []
        # Reduce multiple spaces to a single space
        string = " ".join(string.split())
        # Strip whitespace and replace spaces with underscores
        return [word.strip().replace(" ", "_").capitalize() for word in string.split(",")]

    def __download_image(self, url: str) -> cv2.Mat:
        """
        Downloads an image from a URL.
        Args:
            url: The URL of the image to download.
        Returns:
            The downloaded image as a cv2 Mat.
        """
        response = requests.get(url)
        downloaded_img = np.frombuffer(response.content, dtype="uint8")
        downloaded_img = cv2.imdecode(downloaded_img, cv2.IMREAD_UNCHANGED)
        return downloaded_img

    def __insert_underscores(self, string: str) -> str:
        """
        If the item has spaces it will replace them with underscores.
        Args:
            string: String you want to input underscores to.
        Return:
            Returns the string with underscores within it.
        """
        return string.replace(" ", "_") if " " in string else string

    def __item_info_box(self, item: str) -> str:
        """
        Returns a string of data from the info box for a specific item from the Old School
        RuneScape Wiki.
        Args:
            item: The item name.
        Returns:
            String of json data of the info box or None if the item does not exist or if an error occurred.
        """
        params = {"action": "query", "prop": "revisions", "rvprop": "content", "format": "json", "titles": item}

        try:
            response = requests.get(url=self.base_url + "/api.php", params=params)
            data = response.json()
            pages = data["query"]["pages"]
            page_id = list(pages.keys())[0]
            if int(page_id) < 0:
                return None
            return pages[page_id]["revisions"][0]["*"]
        except requests.exceptions.ConnectionError as e:
            print("Network error:", e)
            return None
        except requests.exceptions.RequestException as e:
            print("Request failed:", e)
            return None

    def __sprite_url(self, item: str) -> str:
        """
        Returns the sprite URL of the item provided.
        Args:
            item: The item name.
        Returns:
            URL of the sprite image (string)
        """
        info_box = self.__item_info_box(item)
        if info_box is None:
            print("page doesn't exist")
            return None
        pattern = r"\[\[File:(.*?)\]\]"
        match = re.search(pattern, info_box)

        if match:
            filename = match.group(1)
            filename = self.__insert_underscores(filename)
            return self.base_url + "images/" + filename

        else:
            print("Sprite couldn't be found in the info box.")
            return None


if __name__ == "__main__":
    scraper = SpriteScraper()

    assert scraper.format_args("") == []
    assert scraper.format_args("a, b, c") == ["A", "B", "C"]
    assert scraper.format_args(" shark ") == ["Shark"]
    assert scraper.format_args(" swordfish ,lobster, lobster   pot ") == ["Swordfish", "Lobster", "Lobster_pot"]
    assert scraper.format_args("Swordfish ,lobster, Lobster_Pot ") == ["Swordfish", "Lobster", "Lobster_pot"]

    assert scraper.capitalize_each_word("swordfish") == "Swordfish"
    assert scraper.capitalize_each_word("Lobster_pot") == "Lobster_Pot"
    assert scraper.capitalize_each_word("arceuus_home_teleport") == "Arceuus_Home_Teleport"
    assert scraper.capitalize_each_word("protect_from_magic") == "Protect_from_Magic"
    assert scraper.capitalize_each_word("teleport_to_house") == "Teleport_to_House"
    assert scraper.capitalize_each_word("claws_of_guthix") == "Claws_of_Guthix"

    scraper.search_and_download(
        search_string=" lobster , lobster  Pot",
        image_type=1,
    )

    scraper.search_and_download(
        search_string="protect from magic, arceuus home teleport, nonexitent_sprite",
        image_type=0,
    )

    print("Test cleared.")
