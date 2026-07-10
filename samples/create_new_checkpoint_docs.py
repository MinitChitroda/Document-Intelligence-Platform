import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw

DIR = "samples/new_test_docs"
os.makedirs(DIR, exist_ok=True)

# 1. Create cookie_recipe.txt
recipe_path = os.path.join(DIR, "cookie_recipe.txt")
recipe_text = """Gourmet Oatmeal Raisin Cookies
==============================
Ingredients:
  - 1 cup butter, softened
  - 1 cup white sugar
  - 1 cup packed brown sugar
  - 2 eggs
  - 1 teaspoon vanilla extract
  - 2 cups all-purpose flour
  - 1 teaspoon baking soda
  - 1 teaspoon salt
  - 1-1/2 teaspoons ground cinnamon
  - 3 cups quick-cooking oats
  - 1 cup raisins

Instructions:
  1. Preheat oven to 375 degrees Fahrenheit (190 degrees Celsius).
  2. In a large bowl, cream together the butter, white sugar, and brown sugar until smooth. Beat in the eggs one at a time, then stir in the vanilla.
  3. Combine the flour, baking soda, salt, and ground cinnamon; stir into the creamed mixture. Mix in the oats and raisins.
  4. Drop by rounded spoonfuls onto ungreased cookie sheets.
  5. Bake for 10 to 12 minutes in the preheated oven, or until light golden brown.
  6. Cool on baking sheets for 5 minutes before transferring to a wire rack to cool completely.
"""
with open(recipe_path, "w", encoding="utf-8") as f:
    f.write(recipe_text)
print(f"Created {recipe_path}")

# 2. Create shipping_policy.pdf using reportlab
policy_path = os.path.join(DIR, "shipping_policy.pdf")
c = canvas.Canvas(policy_path, pagesize=letter)
c.setFont("Helvetica-Bold", 16)
c.drawString(50, 750, "Global Shipping and Delivery Policy")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 710, "1. Shipping Methods & Timelines")
c.setFont("Helvetica", 10)
c.drawString(50, 690, "- Standard Shipping: Takes 3 to 5 business days for domestic deliveries.")
c.drawString(50, 675, "- Express Shipping: Takes 1 to 2 business days for domestic deliveries.")
c.drawString(50, 660, "- International Shipping: Takes 7 to 14 business days depending on location.")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 620, "2. Order Processing Time")
c.setFont("Helvetica", 10)
c.drawString(50, 600, "All orders are processed and packed within 24 hours (1 business day) of order confirmation.")
c.drawString(50, 585, "Orders placed on weekends or holidays will be processed on the following business day.")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 550, "3. Tracking Information")
c.setFont("Helvetica", 10)
c.drawString(50, 530, "Once your order has shipped, a confirmation email with tracking details will be sent.")
c.drawString(50, 515, "Please allow up to 24 hours for the tracking link to display initial scan updates.")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 475, "4. Undelivered Packages")
c.setFont("Helvetica", 10)
c.drawString(50, 455, "If a package is returned due to an incorrect address, the buyer is responsible for return shipping.")
c.drawString(50, 440, "For support or address corrections, email shipping@ourstore.com within 2 hours of checkout.")

c.save()
print(f"Created {policy_path}")

# 3. Create new_receipt.png using Pillow
receipt_path = os.path.join(DIR, "new_receipt.png")
img = Image.new("RGB", (500, 600), color="white")
draw = ImageDraw.Draw(img)

# Use simple draw text to simulate receipt
text_lines = [
    "ORGANIC VEGGIES SUPERMARKET",
    "123 Green Avenue, Boston, MA",
    "=================================",
    "Date: 2026-07-03  Time: 20:18",
    "Receipt ID: REC-99218",
    "---------------------------------",
    "Organic Bananas (1 lb)      $2.99",
    "Fresh Spinach (1 pack)      $3.50",
    "Whole Milk (1 gal)          $4.19",
    "Brown Eggs (1 dozen)        $5.25",
    "---------------------------------",
    "SUBTOTAL:                  $15.93",
    "TAX (6.25%):                $1.00",
    "TOTAL:                     $16.93",
    "=================================",
    "Payment Method: CASH",
    "Thank you for shopping green!"
]

y = 20
for line in text_lines:
    # Use default bitmap font since it is built-in and guaranteed to be present
    draw.text((20, y), line, fill="black")
    y += 30

img.save(receipt_path)
print(f"Created {receipt_path}")
