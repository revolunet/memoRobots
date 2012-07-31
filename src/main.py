# -*- encoding: UTF-8 -*-

#
# simple kivy memory game by julien@revolunet.com
# thats my first try on the awesome kivy framework
# thanks to kivy devs (@tshirtman) for help & tips
#


import os
import random
import kivy
kivy.require('1.4.0')
from kivy.app import App
from kivy.core.window import Window
from kivy.logger import Logger
from kivy.uix.widget import Widget
from kivy.animation import Animation
from kivy.graphics import Quad
from kivy.clock import Clock
from kivy.uix.image import Image
from kivy.uix.modalview import ModalView
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.screenmanager import ScreenManager, Screen, FadeTransition
from kivy.utils import platform
from kivy.properties import NumericProperty, ObjectProperty


class Scaler(Widget):
    """ a scaler for retina display """
    scale = NumericProperty(2)
    container = ObjectProperty(None)

    def __init__(self, **kwargs):
        from kivy.base import EventLoop
        from kivy.lang import Builder
        Builder.load_string('''
<Scaler>:
    container: container
    canvas.before:
        PushMatrix
        Scale:
            scale: root.scale

    canvas.after:
        PopMatrix

    FloatLayout:
        id: container
        size: root.width / root.scale, root.height / root.scale
''')

        super(Scaler, self).__init__(**kwargs)
        EventLoop.add_postproc_module(self)

    def get_parent_window(self):
        return self.container

    def add_widget(self, widget):
        if self.container is not None:
            return self.container.add_widget(widget)
        return super(Scaler, self).add_widget(widget)

    def remove_widget(self, widget):
        if self.container is not None:
            return self.container.remove_widget(widget)
        return super(Scaler, self).remove_widget(widget)

    def process_to_local(self, x, y, relative=False):
        if x is None:
            return None, None
        s = float(self.scale)
        return x / s, y / s

    def process(self, events):
        transform = self.process_to_local
        transformed = []
        for etype, event in events:
            # you might have a move and up event in the same process
            # then avoid the double-transformation
            if event in transformed:
                continue
            transformed.append(event)

            event.sx, event.sy = transform(event.sx, event.sy)
            if etype == 'begin':
                event.osx, event.osy = transform(event.osx, event.osy)
            else:
                # update the delta
                event.dsx = event.sx - event.psx
                event.dsy = event.sy - event.psy
        return events


class QuadWidget(Widget):
    """ a widget with an autostretched Quad Mesh """
    def __init__(self, *args, **kwargs):
        super(QuadWidget, self).__init__(*args, **kwargs)
        self.quad = self.quad_bg = None
        self.bind(size=self.on_sizechange)
        self.init_quads()

    def get_points(self):
        return  (
            self.x,
            self.y,
            self.x + self.width,
            self.y,
            self.x + self.width,
            self.y + self.height,
            self.x,
            self.y + self.height
        )

    def on_sizechange(self, instance, size):
        # needed to fix positions when gridlayout ready or window resize
        if self.quad:
            self.quad_bg.points = self.get_points()
            self.quad.points = self.get_points()

    def init_quads(self):
        points_bg = self.get_points()

        if self.quad:
            self.canvas.before.clear()
            self.canvas.clear()

        # the card itself
        with self.canvas.before:
            self.quad_bg = Quad(points=points_bg)
            self.quad_bg.texture = self.background_back.texture

        # the image displayed
        self.quad = Quad(points=points_bg)
        self.quad.texture = self.picture.texture


class FlippableQuadWidget(QuadWidget):
    """ a QuadWidget that can flip on click"""
    ANIM_DURATION = 0.2                     # flip duration
    ANIM_TYPE = 'quad'                      # anim will pick in/out from anim status
    FLIP_VERTICAL_MATRIX = [                # kinda 'matrix' for Y-axis rotation
        [1, 1, -1, -1, -1, 1, 1, -1],       # closed
        [1, -1, -1, 1, -1, -1, 1, 1],       # semi closed
        [-1, 1, 1, -1, 1, 1, -1, -1],       # opened
        [-1, -1, 1, 1, 1, -1, -1, 1]        # semi opened
    ]

    def __init__(self, *args, **kwargs):
        self.background_front = kwargs.get('background_front')
        self.background_back = kwargs.get('background_back')
        self.picture = kwargs.get('picture')
        self.anim_status = 0                                        # animation status
        self.enabled = True                                         # card is enabled
        self.animating = False                                      # animating
        super(FlippableQuadWidget, self).__init__(*args, **kwargs)

    def update_texture(self):
        # change texture if any
        if self.quad_bg:
            if self.anim_status == 1:
                self.quad_bg.texture = self.background_front.texture
                self.canvas.add(self.quad)
            else:
                self.quad_bg.texture = self.background_back.texture
                self.canvas.remove(self.quad)

    def on_touch_down_custom(self, touch, old_card=None):
        if not self.animating and self.enabled and self.collide_point(touch.x, touch.y):
            Logger.debug('Memory: card touched')
            self.flip()
            return True
        return False

    def flip(self, anim=None):
        """ launch a flip animation """
        if self.animating:
            Logger.error('Memory: cancel flip, already animating')
            return
        if self.anim_status in [0, 2]:
            Logger.info('Memory: started flip from %s' % self.anim_status)
            self.animating = True
            anim = self.next_anim()
            anim.bind(on_complete=self.flip_half)
            anim.start(self.quad)
            anim.start(self.quad_bg)

    def flip_half(self, anim, widget):
        """ called when flip is at 50%. handle the 2nd anim step"""
        if widget == self.quad:
            Logger.debug('Memory: flip half')
            self.update_texture()
            anim = self.next_anim()
            anim.bind(on_complete=self.flip_complete)
            anim.start(self.quad)
            anim.start(self.quad_bg)

    def flip_complete(self, anim, widget):
        if widget == self.quad:
            Logger.debug('Memory: flip complete, status: %s' % self.anim_status)
            self.animating = False

    def get_points(self):
        """ return the quad points for a given flip position """
        points = super(FlippableQuadWidget, self).get_points()
        offsets = (self.width / 2, self.height / 10)
        position = self.anim_status
        pos = 0
        # apply matrix successively
        while pos < position:
            matrix = self.FLIP_VERTICAL_MATRIX[pos]
            offset_matrix = [i * j for i, j in zip(offsets * 4, matrix)]
            points = [i + j for i, j in zip(points, offset_matrix)]
            pos += 1
        return points

    def next_anim(self):
        """ launch next anim step """
        self.anim_status += 1
        self.anim_status %= len(self.FLIP_VERTICAL_MATRIX)
        points = self.get_points()
        transition = '%s_%s' % (['in', 'out'][self.anim_status % 2], self.ANIM_TYPE)
        anim = Animation(d=self.ANIM_DURATION / 2, points=points, t=transition)
        return anim

    def disable(self):
        """ disable the card """
        Logger.debug('Memory: disable card')
        self.enabled = False

    @property
    def disabled(self):
        return not self.enabled


class MemoryCard(FlippableQuadWidget):
    """ a card that store a ref """
    IMAGE_BACK = Image(source='img/card_back.png', allow_stretch=True)
    IMAGE_FRONT = Image(source='img/card_front.png', allow_stretch=True)

    def __init__(self, ref, *args, **kwargs):
        self.ref = ref
        kwargs.setdefault('background_back', self.IMAGE_BACK)
        kwargs.setdefault('background_front', self.IMAGE_FRONT)
        super(MemoryCard, self).__init__(*args, **kwargs)


class GameScreen(Screen):
    def __init__(self, *args, **kwargs):
        super(GameScreen, self).__init__(*args, **kwargs)
        self.game = GameLayout()
        self.add_widget(self.game)

    def start(self):
        self.game.start()


class GameLayout(BoxLayout):
    """ this class is responsible of layout, checking touched card, displaying game info... """
    PAUSE_DURATION = 1
    BUSY = False

    def __init__(self, *args, **kwargs):
        super(GameLayout, self).__init__(*args, **kwargs)
        self.start()

    def start(self):
        Logger.info('Memory: game.start()')
        self.BUSY = False
        self.opened_card = None                                 # track last clicked card
        self.fill()

    def fill(self, nb_cards=8):
        """ fill the grid with random cards """
        Logger.debug('fill GameLayout with %s cards' % nb_cards)
        self.nb_cards_left = self.nb_cards = nb_cards
        self.cards.clear_widgets()
        cardlist = range(self.nb_cards / 2) * 2
        random.shuffle(cardlist)
        images_paths = self.get_random_images()
        for i in range(self.nb_cards):
            ref = cardlist.pop()
            img_path = images_paths[ref]
            card = MemoryCard(
                ref=ref,
                picture=Image(source=img_path, allow_stretch=False)
            )
            card.bind(on_touch_down=self.card_touch)
            self.cards.add_widget(card)

    @property
    def images_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'img', 'robots')

    def get_random_images(self):
        """ choose one random image in each random subdirectory """
        imgs_path = self.images_path
        subdirs = [os.path.join(imgs_path, name) for name in os.listdir(imgs_path) if os.path.isdir(os.path.join(imgs_path, name))]
        random_paths = random.sample(subdirs, self.nb_cards / 2)
        imgs_list = []
        for path in random_paths:
            img = random.choice([os.path.join(path, img) for img in os.listdir(path) if img.endswith('.png')])
            imgs_list.append(img)
        return imgs_list

    def card_touch(self, card, touch):
        """ handle game logic """
        if self.BUSY:
            Logger.debug('Memory: busy, cancel event')
            return True
        if self.opened_card == card:
            Logger.debug('Memory: skip same card')
            return False
        if card.on_touch_down_custom(touch):
            Logger.info('Memory: touched card #%s ' % card.ref)
            if self.opened_card is not None:
                if self.opened_card != card:
                    self.BUSY = True
                    # touched a 2nd different card
                    if self.opened_card.ref == card.ref:
                        Logger.info('Memory: good card touched !')
                        card.disable()
                        self.opened_card.disable()
                        self.nb_cards_left -= 2
                        Clock.schedule_once(self.anim_completes, card.ANIM_DURATION)
                        if self.nb_cards_left == 0:
                            Clock.schedule_once(kivy.app.App.get_running_app().won, card.ANIM_DURATION * 2)
                    else:
                        # incorrect card
                        Logger.warn('Memory: incorrect card touched !')
                        Clock.schedule_once(card.flip, self.PAUSE_DURATION)
                        Clock.schedule_once(self.opened_card.flip, self.PAUSE_DURATION)
                        Clock.schedule_once(self.anim_completes, self.PAUSE_DURATION)
                    self.opened_card = None
            else:
                Logger.info('Memory: picked a first card')
                self.BUSY = True
                self.opened_card = card
                Clock.schedule_once(self.anim_completes, card.ANIM_DURATION)
        return False

    def anim_completes(self, anim):
        self.BUSY = False


class WonPopup(ModalView):
    """ popup when user won """
    def on_open(self):
        print self.image.width
        a = Animation(width=Window.width / 2, height=Window.height / 2, duration=2, t='out_elastic')
        a.start(self)


class HomeScreen(Screen):
    pass


class AboutScreen(Screen):
    pass


class MemoRobotsApp(App):
    use_kivy_settings = False

    def build(self):
        self.screens = ScreenManager(transition=FadeTransition(duration=0.4))
        self.gamescreen = GameScreen(name='game')
        self.screens.add_widget(HomeScreen(name='home'))
        self.screens.add_widget(self.gamescreen)
        self.screens.add_widget(AboutScreen(name='about'))
        parent = Window
        if platform() == 'ios' and (
            Window.width > 2000 or Window.height > 2000):
            self._scaler = Scaler(size=Window.size, scale=2)
            Window.add_widget(self._scaler)
            parent = self._scaler
        parent.add_widget(self.screens)

    def show_home(self):
        Logger.warn('Memory: show_home')
        self.screens.current = 'home'

    def show_game(self):
        Logger.warn('Memory: show_game')
        self.gamescreen.start()
        self.screens.current = 'game'

    def show_about(self):
        Logger.warn('Memory: show_about')
        self.screens.current = 'about'

    def on_pause(self):
        # cancel pause
        return True

    def won(self, anim=None):
        popup = WonPopup()
        popup.open()

    def restart(self):
        self.gamescreen.start()

    def close(self):
        kivy.app.stopTouchApp()

MemoRobotsApp().run()
