import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

DIR = "samples/custom_test_docs"
os.makedirs(DIR, exist_ok=True)

# 1. Create recipe.txt
recipe_path = os.path.join(DIR, "recipe.txt")
recipe_text = """Super Chocolate Cake Recipe
===========================
Ingredients:
  - 2 cups white sugar
  - 1-3/4 cups all-purpose flour
  - 3/4 cup unsweetened cocoa powder
  - 1-1/2 teaspoons baking powder
  - 1-1/2 teaspoons baking soda
  - 1 teaspoon salt
  - 2 eggs
  - 1 cup milk
  - 1/2 cup vegetable oil
  - 2 teaspoons vanilla extract
  - 1 cup boiling water

Instructions:
  1. Heat oven to 350 degrees Fahrenheit (175 degrees Celsius). Grease and flour two 9-inch round baking pans.
  2. Stir together sugar, flour, cocoa, baking powder, baking soda, and salt in a large bowl.
  3. Add eggs, milk, oil, and vanilla; beat on medium speed of mixer for 2 minutes. Stir in boiling water (batter will be thin).
  4. Pour batter into the prepared pans.
  5. Bake for 30 to 35 minutes in the preheated oven, or until a wooden toothpick inserted in the center comes out clean.
  6. Cool completely, then frost as desired.
"""
with open(recipe_path, "w", encoding="utf-8") as f:
    f.write(recipe_text)
print(f"Created {recipe_path}")

# 2. Create return_policy.pdf using reportlab
policy_path = os.path.join(DIR, "return_policy.pdf")
c = canvas.Canvas(policy_path, pagesize=letter)
c.setFont("Helvetica-Bold", 16)
c.drawString(50, 750, "E-Commerce Return and Refund Policy")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 710, "1. Returns Timeline & Window")
c.setFont("Helvetica", 10)
c.drawString(50, 690, "Customers may return any product purchased within 30 days from the delivery date.")
c.drawString(50, 675, "To initiate a return, contact support@ourstore.com with your order number.")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 640, "2. Refund Processing and Timeline")
c.setFont("Helvetica", 10)
c.drawString(50, 620, "Once the returned item is received and inspected at our warehouse, refunds are processed.")
c.drawString(50, 605, "The refund amount will be credited back to your original payment method within 14 business days.")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 570, "3. Conditions Under Which Refund Is NOT Allowed")
c.setFont("Helvetica", 10)
c.drawString(50, 550, "A refund or return will NOT be approved under the following conditions:")
c.drawString(65, 535, "- The request is made after 30 days of the delivery date.")
c.drawString(65, 520, "- The item shows clear signs of use, wear and tear, or physical damage.")
c.drawString(65, 505, "- The product's original packaging or tags have been removed or discarded.")
c.drawString(65, 490, "- The item was purchased under a 'Final Sale' or 'Clearance' promotion.")

c.setFont("Helvetica-Bold", 12)
c.drawString(50, 450, "4. Contact Support")
c.setFont("Helvetica", 10)
c.drawString(50, 430, "For any inquiries or claims, reach us at support@ourstore.com or call 1-800-555-STORE.")

c.save()
print(f"Created {policy_path}")
