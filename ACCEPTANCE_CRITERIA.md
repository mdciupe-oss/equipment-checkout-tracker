[ ] A visitor who is not logged in cannot see or change any equipment or checkout.
[ ] A user can register, log in, and log out. Passwords are stored hashed, never as plain text.
[ ] A user sees only their own department's equipment and checkouts, never another department's.
[ ] Adding an item with a missing name, a duplicate asset tag, or a blank category is rejected with a clear message.
[ ] Checking out an item marks it unavailable and records the borrower and due date.
[ ] An item that's already checked out, or retired, cannot be checked out again.
[ ] A retired item can be reactivated, and it becomes available again.
[ ] Leaving the add or edit form with unsaved changes shows a warning first.
[ ] A due date in the past is rejected at checkout.
[ ] Checking an item back in makes it available again.
[ ] The overview page lists checked-out items, and overdue items are flagged correctly.
[ ] All automated tests pass with one command (pytest).
[ ] The app runs at a public Replit link, and the README explains how to run it locally.