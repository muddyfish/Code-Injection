import infect

passwords = []
def add_password(new, p = passwords):
    p.append(new)

add_password("Hello!")
print passwords
