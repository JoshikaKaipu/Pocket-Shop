#!/usr/bin/env python3
"""Pocket Shop: track art print stock, sales, profit and pricing.

Run:  python3 pocket_shop.py
Data is saved to print_data.json next to this script (standard library only).
"""
import json
import math
import os
import time

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "print_data.json")
state = {"prints": [], "sales": []}


# ---------- storage ----------
def load():
    global state
    try:
        with open(DATA_FILE) as f:
            d = json.load(f)
        if "prints" in d and "sales" in d:
            state = d
    except (OSError, ValueError):
        pass


def save():
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ---------- input helpers ----------
def ask_text(prompt):
    while True:
        s = input(prompt).strip()
        if s:
            return s
        print("  Please enter something.")


def ask_number(prompt, kind=float, minimum=0):
    while True:
        try:
            v = kind(input(prompt).strip().replace("$", ""))
            if v < minimum:
                raise ValueError
            return v
        except ValueError:
            print(f"  Enter a number of at least {minimum}.")


def money(n):
    return f"-${abs(n):,.2f}" if n < 0 else f"${n:,.2f}"


# ---------- calculations ----------
def stats(p):
    sales = [s for s in state["sales"] if s["name"] == p["name"]]
    sold = len(sales)
    rev = sum(s["price"] for s in sales)
    return {
        "sold": sold,
        "left": max(0, p["qty"] - sold),
        "rev": rev,
        "spent": p["qty"] * p["cost"],
        "profit_sold": rev - sold * p["cost"],
        "net": rev - p["qty"] * p["cost"],
        "rate": sold / p["qty"] if p["qty"] else 0,
    }


def totals():
    t = dict(rev=0, spent=0, sold=0, left=0, profit_sold=0, net=0, potential=0)
    for p in state["prints"]:
        s = stats(p)
        t["rev"] += s["rev"]
        t["spent"] += s["spent"]
        t["sold"] += s["sold"]
        t["left"] += s["left"]
        t["profit_sold"] += s["profit_sold"]
        t["net"] += s["net"]
        t["potential"] += s["left"] * (p["price"] - p["cost"])
    return t


def suggest(p):
    """Rule-of-thumb price suggestion. Returns (new_price, reason)."""
    s = stats(p)
    floor = p["cost"] * 1.5
    new = p["price"]
    total_sales = len(state["sales"])
    if s["left"] == 0 and s["sold"] > 0:
        new, why = p["price"] * 1.15, "Sold out. Demand beat supply. Raise the price and reprint."
    elif s["sold"] == 0:
        why = "No sales yet. Hold the price until you have data."
    elif s["rate"] >= 0.6:
        new, why = p["price"] * 1.10, f"Selling fast ({s['rate']:.0%} gone). Room to raise."
    elif s["rate"] < 0.25 and total_sales >= 5:
        new, why = max(floor, p["price"] * 0.90), "Slow compared to the rest. Try a small cut or a bundle."
    else:
        why = "Selling steadily. Hold the price."
    if new < floor:
        new, why = floor, f"Margin is thin (under 50% of cost). Price floor is {money(floor)}."
    new = max(p["cost"] + 0.5, round(new * 2) / 2)
    return new, why


# ---------- screens ----------
def pick_print(prompt="Choose a print"):
    if not state["prints"]:
        print("  No prints yet. Add one first.")
        return None
    for i, p in enumerate(state["prints"], 1):
        print(f"  {i}. {p['name']}  ({stats(p)['left']} left, {money(p['price'])})")
    n = ask_number(f"{prompt} (0 to cancel): ", int, 0)
    if n == 0 or n > len(state["prints"]):
        return None
    return state["prints"][n - 1]


def add_print():
    name = ask_text("Name of print: ")
    if any(p["name"].lower() == name.lower() for p in state["prints"]):
        print("  A print with that name already exists. Use Restock instead.")
        return
    price = ask_number("  Sell price ($): ")
    cost = ask_number("  Print cost each ($): ")
    qty = ask_number("  Number of prints: ", int, 1)
    state["prints"].append({"name": name, "price": price, "cost": cost, "qty": qty})
    save()
    print(f"  Added {name}.")


def first_run_setup():
    print("Welcome! Let's add your prints.")
    n = ask_number("How many types of prints do you have? ", int, 0)
    for i in range(n):
        print(f"\nPrint {i + 1} of {n}")
        add_print()


def sell():
    p = pick_print("Which print sold?")
    if not p:
        return
    if stats(p)["left"] <= 0:
        print("  That print is sold out.")
        return
    state["sales"].append({"name": p["name"], "price": p["price"], "t": time.time()})
    save()
    s = stats(p)
    print(f"  Sold 1 x {p['name']} for {money(p['price'])}. {s['left']} left.")
    print(f"  Net profit so far: {money(totals()['net'])}")


def undo():
    if not state["sales"]:
        print("  Nothing to undo.")
        return
    s = state["sales"].pop()
    save()
    print(f"  Undid sale of {s['name']} ({money(s['price'])}).")


def restock():
    p = pick_print("Restock which print?")
    if not p:
        return
    q = ask_number("  How many more prints? ", int, 1)
    raw = input(f"  Print cost each? (Enter to keep {money(p['cost'])}): ").strip()
    if raw:
        try:
            nc = float(raw.replace("$", ""))
            p["cost"] = (p["qty"] * p["cost"] + q * nc) / (p["qty"] + q)  # blended cost
        except ValueError:
            print("  Not a number, keeping the old cost.")
    p["qty"] += q
    save()
    print(f"  Added {q}. {stats(p)['left']} now in stock.")


def change_price():
    p = pick_print("Change price of which print?")
    if not p:
        return
    p["price"] = ask_number(f"  New price (now {money(p['price'])}): ")
    save()
    print("  Updated. Past sales keep the price they sold at.")


def remove_print():
    p = pick_print("Remove which print?")
    if p and input(f"  Remove {p['name']} and its sales? (y/n): ").lower() == "y":
        state["prints"].remove(p)
        state["sales"] = [s for s in state["sales"] if s["name"] != p["name"]]
        save()
        print("  Removed.")


def summary():
    if not state["prints"]:
        print("  Nothing to summarize yet.")
        return
    t = totals()
    line = "=" * 52
    print(f"\n{line}\n SALES SUMMARY\n{line}")
    print(f" Revenue:               {money(t['rev'])}")
    print(f" Print costs paid:      {money(t['spent'])}")
    print(f" NET PROFIT:            {money(t['net'])}")
    print(f" Profit on sold prints: {money(t['profit_sold'])}")
    print(f" Units sold / left:     {t['sold']} / {t['left']}")
    print(f" Still to earn:         {money(t['potential'])}")

    print(f"\n BEST SELLERS")
    ranked = sorted(state["prints"], key=lambda p: (-stats(p)["sold"], -stats(p)["rev"]))
    top = max(1, stats(ranked[0])["sold"])
    for i, p in enumerate(ranked, 1):
        s = stats(p)
        bar = "#" * round(s["sold"] / top * 20)
        print(f" {i}. {p['name'][:22]:<22} {s['sold']:>3} sold {money(s['rev']):>10}  {bar}")

    print(f"\n UPDATED PRICING")
    for p in state["prints"]:
        new, why = suggest(p)
        be = math.ceil(p["qty"] * p["cost"] / p["price"]) if p["price"] > 0 else 0
        covered = "covered" if stats(p)["sold"] >= be else f"{be - stats(p)['sold']} to go"
        print(f" {p['name']}: {money(p['price'])} -> {money(new)}")
        print(f"    {why}")
        print(f"    Break-even: {be} sold ({covered})")

    print(f"\n NEXT STEPS")
    todo = []
    for p in state["prints"]:
        s = stats(p)
        if s["left"] == 0 and s["sold"] > 0:
            todo.append(f"Reprint {p['name']}. It sold out.")
        elif 0 < s["left"] <= math.ceil(p["qty"] * 0.2) and s["sold"] > 0:
            todo.append(f"{p['name']} is almost gone ({s['left']} left). Plan a reprint.")
        if s["sold"] == 0 and len(state["sales"]) >= 5:
            todo.append(f"{p['name']} has no sales. Try new photos, a bundle, or a lower price.")
    if t["sold"] and t["net"] >= 0:
        todo.append("You are past break-even overall. Put some profit into new prints.")
    elif t["sold"]:
        todo.append(f"You still need {money(-t['net'])} in sales to break even overall.")
    for item in todo or ["Keep logging sales. Suggestions get sharper with more data."]:
        print(f" - {item}")
    print(line)


MENU = [
    ("Sold one", sell),
    ("Calculate summary", summary),
    ("Add a new print", add_print),
    ("Restock a print", restock),
    ("Change a price", change_price),
    ("Undo last sale", undo),
    ("Remove a print", remove_print),
]


def main():
    load()
    if not state["prints"]:
        first_run_setup()
    while True:
        print(f"\n--- POCKET SHOP   net profit {money(totals()['net'])} ---")
        for i, (label, _) in enumerate(MENU, 1):
            print(f" {i}. {label}")
        print(" 0. Quit")
        choice = ask_number("> ", int, 0)
        if choice == 0:
            print("Saved. Bye!")
            break
        if choice <= len(MENU):
            MENU[choice - 1][1]()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\nSaved. Bye!")
