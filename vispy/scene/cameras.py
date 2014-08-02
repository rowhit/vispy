# -*- coding: utf-8 -*-
# Copyright (c) 2014, Vispy Development Team.
# Distributed under the (new) BSD License. See LICENSE.txt for more info.

"""
A brief explanation of how cameras work 
---------------------------------------

The view of a camera is determined by its transform (that it has as
being an entity) and its projection. The former is essentially the
position and orientation of the camera, the latter determines field of
view and any non-linear transform (such as perspective).

The projection must return such a transform that the correct view is
mapped onto the size of the viewbox measured in pixels (i.e.
event.resolution).

The subscene actually has a thrird transform, the viewbox_transform,
which is set by the viewbox and which takes care of the mapping from
pixel coordinates to whatever region the viewbox takes in its parent
viewbox.

"""


from __future__ import division

import numpy as np

from . import transforms
from .entity import Entity
from ..util.event import Event
from ..util.geometry import Rect
from .transforms import (STTransform, PerspectiveTransform, NullTransform,
                         AffineTransform)


def make_camera(cam_type, *args, **kwds):
    cam_types = {
        None: Camera,
        'panzoom': PanZoomCamera,
        'turntable': TurntableCamera,
        }
    
    try: 
        return cam_types[cam_type](*args, **kwds)
    except KeyError:
        raise KeyError('Unknown camera type "%s". Options are: %s' % 
                       (cam_type, cam_types.keys()))


class Camera(Entity):
    """
    Helper class that handles setting the sub-scene transformation of a ViewBox
    and reacts to user input.
    """
    def __init__(self):
        super(Camera, self).__init__()
        self._viewbox = None
        self._transform = NullTransform()

    @property
    def viewbox(self):
        return self._viewbox
    
    @viewbox.setter
    def viewbox(self, vb):
        if self._viewbox is not None:
            self.disconnec()
        self._viewbox = vb
        self.connect()
        self.update()
    
    @property
    def transform(self):
        """
        Transform to apply to the ViewBox's SubScene.
        """
        return self._transform
        
    @transform.setter
    def transform(self, tr):
        self._transform = tr
        self.update()
    
    def connect(self):
        self._viewbox.events.mouse_press.connect(self.mouse_event)
        self._viewbox.events.mouse_release.connect(self.mouse_event)
        self._viewbox.events.mouse_move.connect(self.mouse_event)
        self._viewbox.events.mouse_wheel.connect(self.mouse_event)
    
    def disconnect(self):
        """
        Called by ViewBox.
        
        """
        self._viewbox.events.mouse_press.disconnect(self.mouse_event)
        self._viewbox.events.mouse_release.disconnect(self.mouse_event)
        self._viewbox.events.mouse_move.disconnect(self.mouse_event)
        self._viewbox.events.mouse_wheel.disconnect(self.mouse_event)
    
    def mouse_event(self, event):
        """
        The SubScene received a mouse event; update transform 
        accordingly.
        """
        pass
        
    def resize_event(self, event):
        """
        The ViewBox was resized; update the transform accordingly.
        """
        pass
        
    def update(self):
        """
        Set the scene transform to match the Camera's transform.
        """
        if self.viewbox is not None:
            self.viewbox.scene.transform = self.transform
        





    
class PanZoomCamera(Camera):
    """
    Camera implementing 2D pan/zoom mouse interaction. Primarily intended for
    displaying plot data.
    """
    def __init__(self):
        super(PanZoomCamera, self).__init__()
        self._rect = Rect((0, 0), (1, 1))  # visible range in scene
        self._transform = STTransform()
        self._mouse_enabled = True
        
    @property
    def mouse_enabled(self):
        return self._mouse_enabled
    
    @mouse_enabled.setter
    def mouse_enabled(self, b):
        self._mouse_enabled = b
    
    def mouse_event(self, event):
        """
        The SubScene received a mouse event; update transform 
        accordingly.
        """
        if event.handled or not self._mouse_enabled:
            return
        
        if 1 in event.buttons:
            p1 = np.array(event.last_event.pos)[:2]
            p2 = np.array(event.pos)[:2]
            p1s = self.transform.imap(p1)
            p2s = self.transform.imap(p2)
            self.rect = self.rect + (p1s-p2s)
            event.handled = True
        elif 2 in event.buttons:
            # todo: just access the original event position, rather
            # than mapping to the viewbox and back again.
            p1 = np.array(event.last_event.pos)[:2]
            p2 = np.array(event.pos)[:2]
            p1c = event.map_to_canvas(p1)[:2]
            p2c = event.map_to_canvas(p2)[:2]
            
            s = 1.03 ** ((p1c-p2c) * np.array([1, -1]))
            center = self.transform.imap(event.press_event.pos[:2])
            # TODO: would be nice if STTransform had a nice scale(s, center) 
            # method like AffineTransform.
            transform = (STTransform(translate=center) * 
                         STTransform(scale=s) * 
                         STTransform(translate=-center))
            
            self.rect = transform.map(self.rect)
            event.handled = True
        
        if event.handled:
            self.update()

    def resize_event(self, event):
        self.update()

    @property
    def rect(self):
        return self._rect
        #return self.transform.imap(self.viewbox.rect)
        
    @rect.setter
    def rect(self, args):
        """
        Set the bounding rect of the visible area in the subscene. 
        
        By definition, the +y axis of this rect is opposite the +y axis of the
        ViewBox. 
        """
        if isinstance(args, tuple):
            self._rect = Rect(*args)
        else:
            self._rect = Rect(args)
        self.update()
        
    def update(self):
        if self.viewbox is not None:
            vbr = self.viewbox.rect.flipped(y=True, x=False)
            self.transform.set_mapping(self.rect, vbr)
        super(PanZoomCamera, self).update()

        
class PerspectiveCamera(Camera):
    """ Base class for 3D cameras supporting orthographic and perspective
    projections.
    """
    def __init__(self, mode='ortho'):
        # projection transform and associated options
        self._projection = PerspectiveTransform()
        self.mode = mode
        
        self._ortho = {
            'near': -1e6,
            'far': 1e6,
            'width': 10,
            }
        
        self._perspective = {
            'near': 1e-6,
            'far': 1e6,
            'fov': 60,
            }

        super(PerspectiveCamera, self).__init__()

        # camera transform
        self.transform = AffineTransform()
    
    #@camera.setter
    #def camera(self, cam):
        #if self._camera is not None:
            #trc = self._camera.events.transform_change
            #trc.disconnect(self._update_transform)
        ## convenience: set parent if it's an orphan
        #if not cam.parents and self.viewbox is not None:
            #cam.parent = self.viewbox.scene
        #self._camera = cam
        #self._camera.events.transform_change.connect(self._update_transform)
        #self._update_transform()

    @property
    def viewbox(self):
        return self._viewbox
    
    @viewbox.setter
    def viewbox(self, vb):
        Camera.viewbox.fset(self, vb)
        self.parent = vb.scene
        self._update_transform()
        
    def resize_event(self, event):
        self._update_transform()
    
    def _update_transform(self, event=None):
        if self.viewbox is not None:
            
            # configure camera location / orientation
            # don't loop back to this method while modifying the transform.
            ch_em = self.events.transform_change
            with ch_em.blocker(self._update_transform):
                self._update_entity_transform()
            
            # configure projection transform
            if self.mode == 'ortho': 
                self.set_ortho()
            elif self.mode == 'perspective':
                self.set_perspective()
            else:
                raise ValueError("Unknown projection mode '%s'" % self.mode)
            
            # assemble complete transform mapping to viewbox bounds
            unit = [[-1, 1], [1, -1]]
            vrect = [[0, 0], self.viewbox.size]
            viewbox_tr = STTransform.from_mapping(unit, vrect)
            proj_tr = self._projection
            cam_tr = self.entity_transform(self.viewbox.scene) 
            
            self.transform = viewbox_tr * proj_tr * cam_tr

    def set_perspective(self):
        vbs = self.viewbox.size
        ar = vbs[1] / vbs[0]
        fov = self._perspective['fov']
        near = self._perspective['near']
        far = self._perspective['far']
        self._projection.set_perspective(fov, ar, near, far)

    def set_ortho(self):
        near = self._ortho['near']
        far = self._ortho['far']
        width = self._ortho['width']
        vbs = self.viewbox.size
        height = width * (vbs[1] / vbs[0])
        self._projection.set_ortho(-width/2., width/2., 
                                   -height/2., height/2., 
                                   near, far)

    
class TurntableCamera(PerspectiveCamera):
    """ 3D camera class that orbits around a center point while maintaining a
    fixed vertical orientation.
    """
    def __init__(self, elevation=30, azimuth=30, 
                 distance=10, center=(0, 0, 0), **kwds):
        super(TurntableCamera, self).__init__(**kwds)
        self.elevation = elevation
        self.azimuth = azimuth
        self.distance = distance
        self.center = center
    
    def orbit(self, azim, elev):
        """Orbits the camera around the center position. 
        *azim* and *elev* are given in degrees."""
        self.azimuth += azim
        self.elevation = np.clip(self.elevation + elev, -90, 90)
        self._update_transform()
        
    def mouse_event(self, event):
        """
        The viewbox received a mouse event; update transform 
        accordingly.
        """
        if event.handled:
            return
        
        if event.type == 'mouse_wheel':
            self.fov = self.fov * (1.1**-event.delta[1])
            self._update_transform()
        elif event.type == 'mouse_move' and 1 in event.buttons:
            p1 = np.array(event.last_event.pos)[:2]
            p2 = np.array(event.pos)[:2]
            p1c = event.map_to_canvas(p1)[:2]
            p2c = event.map_to_canvas(p2)[:2]
            d = p2c - p1c
            
            self.orbit(-d[0], d[1])

    def _update_entity_transform(self):
        tr = self.transform
        tr.reset()
        tr.translate(0.0, 0.0, -self.distance)
        tr.rotate(self.azimuth, (0, 1, 0))
        tr.rotate(self.elevation, (-1, 0, 0))
        tr.translate(-np.array(self.center))

class ArcballCamera(PerspectiveCamera):
    pass

class FirstPersonCamera(PerspectiveCamera):
    pass





#class PerspectiveCamera(Camera):
    #"""
    #In progress.

    #"""
    #def __init__(self, parent=None):
        #super(PerspectiveCamera, self).__init__(parent)
    
    #@property
    #def pos(self):
        #raise NotImplementedError()
    
    #@pos.setter
    #def pos(self, pos):
        #self.transform.reset()
        #self.transform.translate(pos)

    #def set_perspective(self, **kwds):
        #self._perspective.update(kwds)
        ## update camera here
        #ar = self._perspective['aspect']
        #near = self._perspective['near']
        #far = self._perspective['far']
        #fov = self._perspective['fov']
        #self._projection.set_perspective(fov, ar, near, far)
        #self.events.projection_change()

    #def set_ortho(self, **kwds):
        #self._perspective.update(kwds)
        ## update camera here
        #ar = self._perspective['aspect']
        #near = self._perspective['near']
        #far = self._perspective['far']
        #fov = self._perspective['fov']
        #self._projection.set_perspective(fov, ar, near, far)
        #self.events.projection_change()

    #def _update_transform(self):
        ## create transform based on look, near, far, fov, and top.
        #self._projection.set_perspective(origin=(0, 0, 0), **self.perspective)

    #def get_projection(self):
        #return self._projection

    #def view_mouse_event(self, event):
        #"""
        #An attached ViewBox received a mouse event;

        #"""
        #pass

#class OrthoCamera(Camera):
    #"""
    #In progress.

    #"""
    #def __init__(self, parent=None):
        #super(OrthoCamera, self).__init__(parent)
        #self._projection = AffineTransform()
        #self.transform = AffineTransform()
        ## TODO: allow self.look to be derived from an Anchor
        #self._perspective = {
            #'near': 1e-6,
            #'far': 1e6,
            #'width': 10,
            #'height': 10,
            #}
    
    #@property
    #def pos(self):
        #raise NotImplementedError()
    
    #@pos.setter
    #def pos(self, pos):
        #self.transform.reset()
        #self.transform.translate(pos)

    #def set_perspective(self, **kwds):
        #self._perspective.update(kwds)
        ## update camera here
        #near = self._perspective['near']
        #far = self._perspective['far']
        #width = self._perspective['width']
        #height = self._perspective['height']
        #self._projection.set_ortho(-width/2., width/2., 
                                   #-height/2., height/2., 
                                   #near, far)
        #self.events.projection_change()

    #def get_projection(self):
        #return self._projection

    #def view_mouse_event(self, event):
        #"""
        #An attached ViewBox received a mouse event;

        #"""
        #pass
