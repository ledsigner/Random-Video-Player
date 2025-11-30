# Random Video Player

## Description:
This is a simple media player that plays videos from a selected folder (and subfolders) in random
order. By default, videos will auto play, but this and other configurations can be changed in the
context menu (right-click anywhere on the video). 

The main window is split into clickable zones for navigation and control:
- Center third: Play/Pause (single click), Fullscreen toggle (double click))
- Left third: Previous video
- Right third: Next video
- Top: Exit fullscreen
- Bottom: Toggle control bar visibility

The control bar at the bottom of the main window has filters for orientation and max length.

Video info is cached in local app data after the initial scan of a folder for faster subsequent 
loading times. If a video is modified or a new file is added to a folder, the cache will be 
updated with the new info.

## Getting Started
The standalone executable can be found here: https://github.com/ledsigner/Random-Video-Player/tree/master/Random%20Video%20Player/dist

## Controls Layout:
(Red is just for reference, not in the actual program)

![Controls Layout](https://raw.githubusercontent.com/ledsigner/Random-Video-Player/refs/heads/master/Random_Video_Player%20layout.png)

![Context Menu](https://raw.githubusercontent.com/ledsigner/Random-Video-Player/refs/heads/master/Context_Menu.png)

## User Guide:
When you open the exe for the first time, you'll be prompted to select a __Home Folder__ and a 
__Play Folder__. 

__Play Folder__: The folder that videos will be played from (including videos in subfolders). 
You can select a Play folder by right clicking anywhere on the video and selecting "Select Play 
Folder".

__Home Folder__: The default folder that will be opened when you click "Select Play Folder". 
You can select a Home folder by right clicking anywhere on the video and selecting "Select Home 
Folder".

When you open the exe after the first time, videos will start playing from the last selected
Play Folder.

## Possible Future Features:
	1. Selectable play order (single selection)
		1.	Shuffle
		2. Name
		3. Date Modified
	2. Media type filter (multi select)
		1. Videos (mp4, mov, m4v, etc...)
		2. Pictures (jpg, jpeg, png, etc...)
		3. Gifs (gif)
	4. Ability to modify tags on the current video
	5. Add current file name to the window title
	6. Next/previous video transition should be seamless, there should be no black frames during the transition
	7. json or settings page for default settings like filters, loop, auto play, etc...
