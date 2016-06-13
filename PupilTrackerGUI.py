#!/Library/Frameworks/Python.framework/Versions/2.7/bin/python

"""
Pupil tracking software.
"""

# Copyright (C) 2016 Alexander Tomlinson
# Distributed under the terms of the GNU General Public License (GPL).

# from sys import platform
import wx
import os
import cv2
import numpy as np


class PupilTracker(object):
    """
    Image processing class.
    """
    def __init__(self, app):
        """
        Constructor.

        :param app: parent window
        """
        self.app = app
        self.cap = None
        self.num_frames = None
        self.frame = None
        self.dx = None
        self.dy = None
        self.orig_image = None
        self.noise_kernel = None
        self.roi_pupil = None
        self.roi_refle = None

    def load_video(self, video_file):
        """
        Creates capture object for video

        :param video_file: video path
        """
        self.cap = cv2.VideoCapture(video_file)
        self.num_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.noise_kernel = np.ones((3, 3), np.uint8)
        self.load_first_frame()

    def load_first_frame(self):
        # draw first frame
        self.next_frame()
        self.app.load_video(self.frame)

        # go back to beginning
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def next_frame(self):
        """
        Gets next frame.

        :return: next frame
        :raise EOFError: if at end of video file
        :raise IOError: if no video file loaded
        """
        if self.cap is not None:
            ret, next_frame = self.cap.read()
            if ret:
                frame = cv2.resize(next_frame, (0, 0), fx=0.5, fy=0.5)
                self.orig_image = frame.copy()
                self.frame = frame
            else:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                # clear locations
                self.roi_pupil = None
                self.roi_refle = None
                self.load_first_frame()
                raise EOFError('Video end.')
        else:
            raise IOError('No video loaded.')

    def get_frame(self):
        """
        Gets the current frame.

        :return: current frame
        """
        if self.frame is not None:
            return self.frame

    def get_orig_frame(self):
        """
        Gets the current frame before any changes were made.

        :return: unedited frame
        :raise AttributeError: if no original frame loaded
        """
        if self.orig_image is not None:
            self.frame = self.orig_image.copy()
            self.roi_pupil = None
            self.roi_refle = None

            return self.orig_image

        else:
            raise AttributeError('Nothing to clear to.')

    def process_image(self, img, roi=None):
        """
        Blurs, grayscales, and shrinks either entire frame or only certain
        region.

        :param img: frame being processed
        :param roi: region of interest being processed
        :return: grayscaled, blurred, shrunken frame
        """
        if roi is not None:
            # roi
            self.dx = roi[0][0]
            self.dy = roi[0][1]
            roi_image = img[roi[0][1]:roi[1][1],
                            roi[0][0]:roi[1][0]]
            # gaussian filter
            gauss = cv2.GaussianBlur(roi_image, (5, 5), 0)

        else:
            self.dx = 0
            self.dy = 0
            # gauss
            gauss = cv2.GaussianBlur(img, (5, 5), 0)

        gray = cv2.cvtColor(gauss, cv2.COLOR_BGR2GRAY)

        return gray

    def find_pupils(self, roi=None):
        """
        Searches for possible pupils in processed image

        :param roi: region of interest
        :return: list of possible pupil contours
        """
        # roi and gauss
        grayed = self.process_image(self.frame, roi)
        # threshold and remove noise
        _, thresh_pupil = cv2.threshold(grayed, 45, 255, cv2.THRESH_BINARY)
        filtered_pupil = cv2.morphologyEx(thresh_pupil, cv2.MORPH_CLOSE,
                                          self.noise_kernel, iterations=4)
        # find contours
        _, contours_pupil, _ = cv2.findContours(filtered_pupil, cv2.RETR_TREE,
                                                cv2.CHAIN_APPROX_SIMPLE)

        found_pupils = []
        # process contours
        if len(contours_pupil) != 0:
            for cnt in contours_pupil:

                # drop small and large
                area = cv2.contourArea(cnt)
                if area == 0:
                    continue

                if not 1000 < area < 5000:
                    continue

                # drop too few points
                hull = cv2.convexHull(cnt)
                if hull.shape[0] < 5:
                    continue

                # drop too eccentric
                circumference = cv2.arcLength(hull, True)
                circularity = circumference ** 2 / (4*np.pi*area)
                if circularity >= 1.6:
                    continue

                # rescale to full image
                hull[:, :, 0] += self.dx
                hull[:, :, 1] += self.dy

                found_pupils.append(hull)

        return found_pupils

    def draw_pupil(self, index=None, roi=None, verbose=True):
        """
        Draws the currently selected pupil to the frame.

        :param index: which pupil in the list of possible pupils to draw
        :param roi: region of interest
        :param verbose: if true, draws extra content to the frame (roi, etc)
        :raise AttributeError: if list of pupils is empty
        """
        if index is None:
            index = 0

        cnt_list = self.find_pupils(roi)

        if len(cnt_list) > 0:
            cnt = cnt_list[index]
        else:
            raise AttributeError('No pupils found.')

        # fit ellipse
        ellipse = cv2.fitEllipse(cnt)

        # centroid
        cx = int(ellipse[0][0])
        cy = int(ellipse[0][1])

        # draw
        cv2.circle(self.frame, (cx, cy), 2, (255,255,255))
        if verbose:
            cv2.drawContours(self.frame, cnt, -1, (0, 0, 255), 2)
            cv2.ellipse(self.frame, ellipse, (0, 255, 100), 1)
            cv2.rectangle(self.frame, (cx-100, cy-100), (cx+100, cy+100), (255, 255,
                                                                    255))

        self.roi_pupil = [(cx - 100, cy - 100), (cx + 100, cy + 100)]

    def track_pupil(self):
        """
        Makes call to draw pupil with proper roi and handles errors.
        """
        if self.roi_pupil is not None:
            try:
                self.draw_pupil(roi=self.roi_pupil)
            except IndexError as e:
                # print e
                pass
            except AttributeError as e:
                # print e
                pass
        else:
            pass

    def find_refle(self, roi=None):
        """
        Searches for possible reflections in processed image

        :param roi: region of interest
        :return: list of possible reflection contours
        """
        # roi and gauss
        grayed = self.process_image(self.frame, self.roi_pupil)
        # threshold and remove noise
        _, thresh_refle = cv2.threshold(grayed, 200, 255, cv2.THRESH_BINARY)
        filtered_refle = cv2.morphologyEx(thresh_refle, cv2.MORPH_CLOSE,
                                          self.noise_kernel, iterations=2)
        # find contours
        _, contours_refle, _ = cv2.findContours(filtered_refle, cv2.RETR_TREE,
                                                cv2.CHAIN_APPROX_SIMPLE)

        found_reflections = []
        # process contours
        if len(contours_refle) != 0:
            for cnt in contours_refle:

                # drop small and large
                area = cv2.contourArea(cnt)
                if area == 0:
                    continue

                if not 25 < area < 500:
                    continue

                # rescale to full image
                cnt[:, :, 0] += self.dx
                cnt[:, :, 1] += self.dy

                # test squareness
                rect = cv2.minAreaRect(cnt)
                w, h = rect[1][0], rect[1][1]
                squareness = h/w
                if not 0.5 < squareness < 2:
                    continue

                # see if center in roi
                if roi is not None:
                    # rect center
                    cx = int(rect[0][0])
                    cy = int(rect[0][1])
                    if not self.roi_refle[0][0] < cx < self.roi_refle[1][0] \
                            or not \
                            self.roi_refle[0][1] < cy < self.roi_refle[1][1]:
                        continue

                found_reflections.append(cnt)

        return found_reflections

    def draw_refle(self, index=None, roi=None, verbose=True):
        """
        Draws the currently selected reflection to the frame.

        :param index: which pupil in the list of possible reflections to draw
        :param roi: region of interest
        :param verbose: if true, draws extra content to the frame (roi, etc)
        :raise AttributeError: if list of reflections is empty
        """
        if index is None:
            index = 0

        cnt_list = self.find_refle(roi)

        if len(cnt_list) > 0:
            cnt = cnt_list[index]
        else:
            raise AttributeError('No reflections found.')

        rect = cv2.minAreaRect(cnt)
        box = cv2.boxPoints(rect)
        box = np.int0(box)

        # rect center
        cx = int(rect[0][0])
        cy = int(rect[0][1])

        # reset roi
        self.roi_refle = [(cx - 15, cy - 15), (cx + 15, cy + 15)]

        # draw
        cv2.circle(self.frame, (cx, cy), 2, (100, 100, 100))
        if verbose:
            cv2.rectangle(self.frame, (cx-15, cy-15), (cx+15, cy+15), (255, 255, 255))
            cv2.drawContours(self.frame, cnt, -1, (0, 0, 255), 2)
            cv2.drawContours(self.frame, [box], 0, (0, 255, 100), 1)

    def track_refle(self):
        """
        Makes call to draw reflection with proper roi and handles errors.
        """
        if self.roi_refle is not None:
            try:
                self.draw_refle(roi=self.roi_refle)
            except IndexError as e:
                # print e
                pass
            except AttributeError as e:
                # print e
                pass
        else:
            pass


class ImagePanel(wx.Panel):
    """
    Class for panel holding the images of the rabbit eyes.

    :param parent: parent window panel (MyFrame in this case)
    """
    def __init__(self, parent):
        """
        Constructor
        """
        # super instantiation
        super(ImagePanel, self).__init__(parent, size=(960, 540))

        # instance attributes
        self.app = parent
        # self.image_ctrl = wx.StaticBitmap(self)
        self.image_bmp = None
        self.orig_image = None

        self.SetDoubleBuffered(True)
        self.fps = 60
        self.fps_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.draw, self.fps_timer)
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def start_timer(self):
        self.fps_timer.Start(1000/self.fps)

    def stop_timer(self):
        self.fps_timer.Stop()

    def load_image(self, img):
        """
        Creates buffer loader and loads first image
        """
        self.image_bmp = wx.BitmapFromBuffer(960, 540, img)
        self.Refresh()

    def draw(self, evt=None):
        """
        Draws drawings.
        """
        if self.app.playing:
            try:
                self.app.tracker.next_frame()
            except EOFError as e:
                print e
                self.app.playing = False
                self.stop_timer()
                return
            except IOError as e:
                print e
                self.app.playing = False
                self.stop_timer()
                return

            self.app.tracker.track_pupil()
            self.app.tracker.track_refle()

        self.image_bmp.CopyFromBuffer(self.app.tracker.get_frame())
        self.Refresh()

        if evt is not None:
            evt.Skip()

    def on_paint(self, evt):
        if self.image_bmp is not None:
            dc = wx.BufferedPaintDC(self)
            dc.Clear()
            dc.DrawBitmap(self.image_bmp, 0, 0)
        evt.Skip()


class ToolsPanel(wx.Panel):
    """
    Class for panel with buttons.
    """
    def __init__(self, parent):
        """
        Constructor
        """
        # super instantiation
        super(ToolsPanel, self).__init__(parent)

        # instance attributes
        self.app = parent
        self.pupil_index = -1
        self.refle_index = -1

        # find buttons
        self.find_pupil_button = wx.Button(self, label='Find pupil')
        self.find_refle_button = wx.Button(self, label='Find refle')
        self.clear_button = wx.Button(self, label='Clear')
        self.load_button = wx.Button(self, label='Load')
        self.play_button = wx.Button(self, label='Play')
        self.stop_button = wx.Button(self, label='Stop')

        # button sizer
        button_sizer = wx.BoxSizer(wx.VERTICAL)

        # add buttons to sizer
        button_sizer.Add(self.find_pupil_button,
                         flag=wx.LEFT | wx.RIGHT,
                         border=5)
        button_sizer.Add(self.find_refle_button,
                         flag=wx.LEFT | wx.RIGHT,
                         border=5)
        button_sizer.Add(self.clear_button,
                         flag=wx.LEFT | wx.RIGHT,
                         border=5)
        button_sizer.Add(self.load_button,
                         flag=wx.LEFT | wx.RIGHT,
                         border=5)
        button_sizer.Add(self.play_button,
                         flag=wx.LEFT | wx.RIGHT,
                         border=5)
        button_sizer.Add(self.stop_button,
                         flag=wx.LEFT | wx.RIGHT,
                         border=5)

        # event binders
        self.Bind(wx.EVT_BUTTON,
                  self.on_find_pupil_button,
                  self.find_pupil_button)
        self.Bind(wx.EVT_BUTTON,
                  self.on_find_refle_button,
                  self.find_refle_button)
        self.Bind(wx.EVT_BUTTON,
                  self.on_clear_button,
                  self.clear_button)
        self.Bind(wx.EVT_BUTTON,
                  self.on_load_button,
                  self.load_button)
        self.Bind(wx.EVT_BUTTON,
                  self.on_play_button,
                  self.play_button)
        self.Bind(wx.EVT_BUTTON,
                  self.on_stop_button,
                  self.stop_button)

        # set sizer
        self.SetSizer(button_sizer)

    def on_find_pupil_button(self, evt):
        try:
            self.pupil_index += 1
            self.app.draw_pupil(self.pupil_index)
        except IndexError:
            self.pupil_index = -1
            self.on_find_pupil_button(evt)
        except AttributeError as e:
            print e

    def on_find_refle_button(self, evt):
        try:
            self.refle_index += 1
            self.app.draw_refle(self.pupil_index, self.refle_index)
        except IndexError:
            self.refle_index = -1
            self.on_find_refle_button(evt)
        except AttributeError as e:
            print e

    def on_clear_button(self, evt):
        try:
            self.app.clear(draw=True)
            # self.app.draw()
        except AttributeError as e:
            print e
            return
        self.pupil_index = -1
        self.refle_index = -1

    def on_load_button(self, evt):
        self.pupil_index = -1
        self.refle_index = -1

        self.app.load_dialog()

    def on_play_button(self, evt):
        self.pupil_index = -1
        self.refle_index = -1

        self.app.play()

    def on_stop_button(self, evt):
        self.app.stop()


class MyFrame(wx.Frame):
    """
    Class for generating main frame. Holds other panels.
    """
    def __init__(self):
        """
        Constructor
        """
        # super instantiation
        super(MyFrame, self).__init__(None, title='PupilTracker', size=(960, 540))

        self.playing = False

        # instantiate tracker
        self.tracker = PupilTracker(self)

        self.image_panel = ImagePanel(self)
        self.tools_panel = ToolsPanel(self)

        # sizer for panels
        panel_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # add panels to sizer
        panel_sizer.Add(self.image_panel,
                        flag=wx.EXPAND)
        panel_sizer.Add(self.tools_panel,
                        flag=wx.EXPAND)

        # set sizer
        self.SetSizer(panel_sizer)
        panel_sizer.Fit(self)

        # draw frame
        self.Show()

    def draw(self):
        self.image_panel.draw()

    def load_dialog(self):
        default_dir = os.path.abspath(
            r'C:\Users\Alex\PycharmProjects\EyeTracker\vids')

        # popup save dialog
        load_dialog = wx.FileDialog(self,
                                    message='File path',
                                    defaultDir=default_dir,
                                    # wildcard='*.txt',
                                    style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

        # to exit out of popup on cancel button
        if load_dialog.ShowModal() == wx.ID_CANCEL:
            return

        # get path from save dialog and open
        video_file = load_dialog.GetPath()
        self.open_video(video_file)

    def open_video(self, video_file):
        self.tracker.load_video(video_file)

    def load_video(self, img):
        self.image_panel.load_image(img)

    def draw_pupil(self, pupil_index):
        self.clear()
        if pupil_index != -1:
            self.tracker.draw_pupil(index=pupil_index, verbose=True)
        self.image_panel.draw()

    def draw_refle(self, pupil_index, refle_index):
        self.clear()
        if pupil_index != -1:
            self.tracker.draw_pupil(index=pupil_index, verbose=True)
            self.image_panel.draw()
        self.tracker.draw_refle(index=refle_index, verbose=True)
        self.image_panel.draw()

    def clear(self, draw=False):
        self.tracker.get_orig_frame()
        if draw:
            self.draw()

    def play(self):
        self.image_panel.start_timer()
        self.playing = True

    def stop(self):
        self.image_panel.stop_timer()
        self.playing = False


def main():
    """
    Main function to start GUI
    """
    # instantiate app
    global app
    app = wx.App(False)
    # instantiate window
    frame = MyFrame()
    # run app
    app.MainLoop()

if __name__ == '__main__':
    main()