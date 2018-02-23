#!/usr/bin/env python

from direct.showbase.ShowBase import ShowBase
from panda3d.core import TextNode, TransparencyAttrib
from panda3d.core import LPoint3, LVector3, deg2Rad
from direct.gui.OnscreenText import OnscreenText
from direct.task.Task import Task
from math import sin, cos, pi
from random import randint, choice, random, randint
from direct.interval.MetaInterval import Sequence
from direct.interval.FunctionInterval import Wait, Func
import sys

# Constants that will control the behavior of the game. It is good to
# group constants like this so that they can be changed once without
# having to find everywhere they are used in code
SPRITE_POS = 55     # At default field of view and a depth of 55, the screen
# dimensions is 40x30 units
SCREEN_X = 20       # Screen goes from -20 to 20 on X
SCREEN_Y = 15       # Screen goes from -15 to 15 on Y
TURN_RATE = 360     # Degrees ship can turn in 1 second
ACCELERATION = 10   # Ship acceleration in units/sec/sec
MAX_VEL = 6         # Maximum ship velocity in units/sec
MAX_VEL_SQ = MAX_VEL ** 2  # Square of the ship velocity
DEG_TO_RAD = pi / 180  # translates degrees to radians for sin and cos
BULLET_LIFE = 2     # How long bullets stay on screen before removed
BULLET_REPEAT = .2  # How often bullets can be fired
BULLET_SPEED = 10   # Speed bullets move
AST_INIT_VEL = 1    # Velocity of the largest asteroids
AST_INIT_SCALE = 3  # Initial asteroid scale
AST_VEL_SCALE = 2.2  # How much asteroid speed multiplies when broken up
AST_SIZE_SCALE = .6  # How much asteroid scale changes when broken up
AST_MIN_SCALE = 1.1  # If and asteroid is smaller than this and is hit,
# it disapears instead of splitting up


# This helps reduce the amount of code used by loading objects, since all of
# the objects are pretty much the same.
def loadObject(tex=None, pos=LPoint3(0, 0), depth=SPRITE_POS, scale=1,
               transparency=True):
    # Every object uses the plane model and is parented to the camera
    # so that it faces the screen.
    obj = loader.loadModel("models/plane")
    obj.reparentTo(camera)

    # Set the initial position and scale.
    obj.setPos(pos.getX(), depth, pos.getY())
    obj.setScale(scale)

    # This tells Panda not to worry about the order that things are drawn in
    # (ie. disable Z-testing).  This prevents an effect known as Z-fighting.
    obj.setBin("unsorted", 0)
    obj.setDepthTest(False)

    if transparency:
        # Enable transparency blending.
        obj.setTransparency(TransparencyAttrib.MAlpha)

    if tex:
        # Load and set the requested texture.
        tex = loader.loadTexture("textures/" + tex)
        obj.setTexture(tex, 1)

    return obj


# Macro-like function used to reduce the amount to code needed to create the
# on screen instructions
def genLabelText(text, i):
    return OnscreenText(text=text, parent=base.a2dTopLeft, pos=(0.07, -.06 * i - 0.1),
                        fg=(1, 1, 1, 1), align=TextNode.ALeft, shadow=(0, 0, 0, 0.5), scale=.05)


class AsteroidsDemo(ShowBase):

    def __init__(self):
        # Initialize the ShowBase class from which we inherit, which will
        # create a window and set up everything we need for rendering into it.
        ShowBase.__init__(self)

        # This code puts the standard title and instruction text on screen
        self.title = OnscreenText(text="Panda3D: Tutorial - Tasks",
                                  parent=base.a2dBottomRight, scale=.07,
                                  align=TextNode.ARight, pos=(-0.1, 0.1),
                                  fg=(1, 1, 1, 1), shadow=(0, 0, 0, 0.5))
        self.escapeText = genLabelText("ESC: Quit", 0)
        self.leftkeyText = genLabelText("[Left Arrow]: Turn Left (CCW)", 1)
        self.rightkeyText = genLabelText("[Right Arrow]: Turn Right (CW)", 2)
        self.spacekeyText = genLabelText("[Space Bar]: Fire", 3)

        # Disable default mouse-based camera control.  This is a method on the
        # ShowBase class from which we inherit.
        self.disableMouse()

        # Load the background starfield.
        self.setBackgroundColor((0, 0, 0, 1))
        self.bg = loadObject("stars.jpg", scale=146, depth=200,
                             transparency=False)

        # Load the ship and set its initial velocity.
        self.ship = loadObject("ship.png", pos=LPoint3(0, -12, 0))
        self.setVelocity(self.ship, LVector3.zero())

        # A dictionary of what keys are currently being pressed
        # The key events update this list, and our task will query it as input
        self.keys = {"turnLeft": 0, "turnRight": 0,
                     "accel": 0, "fire": 0}

        self.accept("escape", sys.exit)  # Escape quits
        # Other keys events set the appropriate value in our key dictionary
        self.accept("arrow_left",     self.setKey, ["turnLeft", 1])
        self.accept("arrow_left-up",  self.setKey, ["turnLeft", 0])
        self.accept("arrow_right",    self.setKey, ["turnRight", 1])
        self.accept("arrow_right-up", self.setKey, ["turnRight", 0])
        self.accept("arrow_up",       self.setKey, ["accel", 1])
        self.accept("arrow_up-up",    self.setKey, ["accel", 0])
        self.accept("space",          self.setKey, ["fire", 1])

        # Now we create the task. taskMgr is the task manager that actually
        # calls the function each frame. The add method creates a new task.
        # The first argument is the function to be called, and the second
        # argument is the name for the task.  It returns a task object which
        # is passed to the function each frame.
        self.gameTask = taskMgr.add(self.gameLoop, "gameLoop")
        # Task to spawning the asteroids.
        self.asteroidsTask = taskMgr.add(self.spawnAsteroids, "spawnAsteroids")

        # Stores the time at which the next bullet may be fired.
        self.nextBullet = 0.0
        self.alive = True
        self.asteroids = []

        # This list will stored fired bullets.
        self.bullets = []


    # As described earlier, this simply sets a key in the self.keys dictionary
    # to the given value.
    def setKey(self, key, val):
        self.keys[key] = val

    def setVelocity(self, obj, val):
        obj.setPythonTag("velocity", val)

    def getVelocity(self, obj):
        return obj.getPythonTag("velocity")

    def setExpires(self, obj, val):
        obj.setPythonTag("expires", val)

    def getExpires(self, obj):
        return obj.getPythonTag("expires")

    def spawnAsteroids(self, task):
        if not self.alive:
            return Task.cont

        if len(self.asteroids) <= 3:
            # This loads an asteroid. The texture chosen is random
            # from "asteroid1.png" to "asteroid3.png".
            asteroid = loadObject(f'asteroid{randint(1, 3)}.png',
                                  scale=AST_INIT_SCALE)
            self.asteroids.append(asteroid)

            asteroid.setX(choice(tuple(range(-SCREEN_X, SCREEN_X))))
            # Y
            asteroid.setZ(choice(tuple(range(-SCREEN_Y + 15, SCREEN_Y))))

            # Heading is a random angle in degrees, only for down
            heading = deg2Rad(randint(110, 250))

            # Converts the heading to a vector and multiplies it by speed to
            # get a velocity vector
            v = LVector3(sin(heading), 0, cos(heading)) * AST_INIT_VEL
            self.setVelocity(asteroid, v)

        return Task.cont

    def clearAsteroids(self):
        self.asteroids.clear()
        self.asteroids = []
        self.alive = True

    # This is our main task function, which does all of the per-frame
    # processing.  It takes in self like all functions in a class, and task,
    # the task object returned by taskMgr.
    def gameLoop(self, task):
        # Get the time elapsed since the next frame.  We need this for our
        # distance and velocity calculations.
        dt = globalClock.getDt()

        # If the ship is not alive, do nothing.  Tasks return Task.cont to
        # signify that the task should continue running. If Task.done were
        # returned instead, the task would be removed and would no longer be
        # called every frame.
        if not self.alive:
            return Task.cont

        # update ship position
        self.updateShip(dt)

        # check to see if the ship can fire
        if self.keys["fire"] and task.time > self.nextBullet:
            self.fire(task.time)  # If so, call the fire function
            # And disable firing for a bit
            self.nextBullet = task.time + BULLET_REPEAT
        # Remove the fire flag until the next spacebar press
        self.keys["fire"] = 0

        # update asteroids
        for obj in self.asteroids:
            self.updatePos(obj, dt)

        # update bullets
        newBulletArray = []
        for obj in self.bullets:
            self.updatePos(obj, dt)  # Update the bullet
            # Bullets have an experation time (see definition of fire)
            # If a bullet has not expired, add it to the new bullet list so
            # that it will continue to exist.
            if self.getExpires(obj) > task.time:
                newBulletArray.append(obj)
            else:
                obj.removeNode()  # Otherwise, remove it from the scene.
        # Set the bullet array to be the newly updat3ed array
        self.bullets = newBulletArray

        # Check bullet collision with asteroids
        # In short, it checks every bullet against every asteroid. This is
        # quite slow.  A big optimization would be to sort the objects left to
        # right and check only if they overlap.  Framerate can go way down if
        # there are many bullets on screen, but for the most part it's okay.
        for bullet in self.bullets:
            # This range statement makes it step though the asteroid list
            # backwards.  This is because if an asteroid is removed, the
            # elements after it will change position in the list.  If you go
            # backwards, the length stays constant.
            for i in range(len(self.asteroids) - 1, -1, -1):
                asteroid = self.asteroids[i]
                # Panda's collision detection is more complicated than we need
                # here.  This is the basic sphere collision check. If the
                # distance between the object centers is less than sum of the
                # radii of the two objects, then we have a collision. We use
                # lengthSquared() since it is faster than length().
                if ((bullet.getPos() - asteroid.getPos()).lengthSquared() <
                    (((bullet.getScale().getX() + asteroid.getScale().getX())
                      * .5) ** 2)):
                    # Schedule the bullet for removal
                    self.setExpires(bullet, 0)
                    self.asteroidHit(i)      # Handle the hit

        # Now we do the same collision pass for the ship
        shipSize = self.ship.getScale().getX()
        for ast in self.asteroids:
            # Same sphere collision check for the ship vs. the asteroid
            if ((self.ship.getPos() - ast.getPos()).lengthSquared() <
                    (((shipSize + ast.getScale().getX()) * .5) ** 2)):
                # If there is a hit, clear the screen and schedule a restart
                self.alive = False         # Ship is no longer alive
                # Remove every object in asteroids and bullets from the scene
                for i in self.asteroids + self.bullets:
                    i.removeNode()
                self.bullets = []          # Clear the bullet list
                self.ship.hide()           # Hide the ship
                # Reset the velocity
                self.setVelocity(self.ship, LVector3(0, 0, 0))
                Sequence(Wait(2),          # Wait 2 seconds
                         Func(self.ship.setX, 0),  # Reset position X
                         Func(self.ship.show),     # Show the ship
                         Func(self.clearAsteroids)).start()  # clear asteroids
                return Task.cont

        return Task.cont    # Since every return is Task.cont, the task will
        # continue indefinitely

    # Updates the positions of objects and remove asteroid if go out
    def updatePos(self, obj, dt):
        vel = self.getVelocity(obj)
        newPos = obj.getPos() + (vel * dt)

        # Check if the object is out of bounds. If so, wrap it
        radius = .5 * obj.getScale().getX()
        if newPos.getX() - radius > SCREEN_X:
            newPos.setX(-SCREEN_X)
        elif newPos.getX() + radius < -SCREEN_X:
            newPos.setX(SCREEN_X)
        elif newPos.getZ() + radius < -SCREEN_Y:  # for screen down
            if obj in self.asteroids:
                index = self.asteroids.index(obj)
                obj.removeNode()
                del self.asteroids[index]
                return
        elif newPos.getZ() + radius > SCREEN_Y:  # for screen down
            if obj in self.asteroids:
                index = self.asteroids.index(obj)
                obj.removeNode()
                del self.asteroids[index]
                return
        obj.setPos(newPos)

    # The handler when an asteroid is hit by a bullet
    def asteroidHit(self, index):
        # If the asteroid is small it is simply removed
        if self.asteroids[index].getScale().getX() <= AST_MIN_SCALE:
            self.asteroids[index].removeNode()
            # Remove the asteroid from the list of asteroids.
            del self.asteroids[index]
        else:
            # If it is big enough, divide it up into little asteroids.
            # First we update the current asteroid.
            asteroid = self.asteroids[index]
            newScale = asteroid.getScale().getX() * AST_SIZE_SCALE
            asteroid.setScale(newScale)  # Rescale it

            # The new direction is chosen as perpendicular to the old direction
            # This is determined using the cross product, which returns a
            # vector perpendicular to the two input vectors.  By crossing
            # velocity with a vector that goes into the screen, we get a vector
            # that is orthagonal to the original velocity in the screen plane.
            vel = self.getVelocity(asteroid)
            speed = vel.length() * AST_VEL_SCALE
            vel.normalize()
            vel = LVector3(0, 1, 0).cross(vel)
            vel *= speed
            self.setVelocity(asteroid, vel)

            # Now we create a new asteroid identical to the current one
            newAst = loadObject(scale=newScale)
            self.setVelocity(newAst, vel * -1)
            newAst.setPos(asteroid.getPos())
            newAst.setTexture(asteroid.getTexture(), 1)
            self.asteroids.append(newAst)

    # This updates the ship's position. This is similar to the general update
    # but takes into account turn and thrust
    def updateShip(self, dt):
        # Change heading if left or right is being pressed
        if self.keys["turnRight"]:
            newPos = self.ship.getPos()
            newPos.setX(newPos.getX() + (MAX_VEL * dt))
            self.ship.setPos(newPos)
        elif self.keys["turnLeft"]:
            newPos = self.ship.getPos()
            newPos.setX(newPos.getX() - (MAX_VEL * dt))
            self.ship.setPos(newPos)

    # Creates a bullet and adds it to the bullet list
    def fire(self, time):
        direction = DEG_TO_RAD * self.ship.getR()
        pos = self.ship.getPos()
        bullet = loadObject("bullet.png", scale=.2)  # Create the object
        bullet.setPos(pos)
        # Velocity is in relation to the ship
        vel = (self.getVelocity(self.ship) +
               (LVector3(sin(direction), 0, cos(direction)) *
                BULLET_SPEED))
        self.setVelocity(bullet, vel)
        # Set the bullet expiration time to be a certain amount past the
        # current time
        self.setExpires(bullet, time + BULLET_LIFE)

        # Finally, add the new bullet to the list
        self.bullets.append(bullet)

# We now have everything we need. Make an instance of the class and start
# 3D rendering
demo = AsteroidsDemo()
demo.run()
