import matplotlib.pyplot as plt
import numpy as np
from random import randint

#Everything before "image = plt.imread(image)" is just on ellas request, before we actually submit it would be replaced
choice = input("Tall (T) or Wide (W)")
while choice.upper() != "T" and choice.upper() != "W":
    choice = input("Tall (T) or Wide (W)")
if choice.upper() == "T":
    ella_hugo_BOSS_ulbrich = randint(1,22)
    if ella_hugo_BOSS_ulbrich == 7:
        image = "Tall2.jpg"
        #Thales: 80 wide, 134 high
    else:
        image = "Tall1.jpg"
        #Ella: 80 wide, 155 high
else:
    image = "aWide.jpg"
    #164 wide, 80 high

image = plt.imread(image)
scale = 3
size = max(image.shape[0],image.shape[1])*scale
canvas = np.zeros((size, int(size*1.5), image.shape[2]), dtype=np.uint8)
canvas += 255
f = int(0.5*image.shape[1])
start_x = int(0.6*image.shape[1])
start_y = int(-0.9*image.shape[0])
for y in range(image.shape[0]):
    for x in range(image.shape[1]):
        colour = image[y, x]
        old_x = x + start_x
        old_y = y + start_y
        new_x = -int((f*old_x) / (old_x-f))
        new_y = int((old_y/old_x)*new_x)
        try:
            canvas[(size//2)+old_y, (3*size//4)+old_x] = colour
        except:
            continue
        for dy in range(-10, 11):
            for dx in range(-10, 11):
                try:
                    canvas[(size//2)+new_y+dy, (3*size//4)+new_x+dx] = colour
                except:
                    continue

plt.imshow(canvas, extent=[-size*1.5, size*1.5, -size, size])
plt.xlim(-size*1.5, size*1.5)
plt.ylim(-size, size)
plt.axvline(x=0)
plt.scatter(f, 0, color='red', marker='*')
plt.scatter(-f, 0, color='red', marker='*')
