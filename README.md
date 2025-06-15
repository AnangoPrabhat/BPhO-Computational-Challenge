# BPhO-Computational-Challenge
The [BPhO Computational Challenge](https://www.bpho.org.uk/bpho/computational-challenge/), run by the British Physics Olympiad, is a competition for solving physics problems computationally. In 2025, the topic is optics. 

This project consists of our solution to the BPhO Computational Challenge 2025 Optics Tasks. We have developed a website (/Website) to show our solutions for the tasks interactively, and a vision demonstration (/vision_project) website containing an interactive simulation of the eye's lens and an eye test game.

Our solutions to the Ray Optics Problems and our report on the challenge are also included here.

We also created an app for each of the websites, which can currently be downloaded using the APK files in /APKs. To install these APKs, you must enable "Install from unknown sources" in your Android settings. This setting can expose your device to security risks. We guarantee that the provided APKs are built directly from the source code in this repository and contain no malicious code, however, for maximum security, use the websites.

Acknowledgments:

Parts of the development of this project utilised Google's Gemini 2.5 Pro for its reasoning and coding capabilities. Specifically, for the main tasks website, much of it was previously done in jupyter notebook using ipywidgets, but when we tried to scale this into a whole website the ipywidgets sliders did not work well. Therefore, we used AI assistance to convert the ipywidgets sliders into JavaScript sliders, and for handling some parts of the Flask application code. For the vision simulator and eye test game website, we used AI assistance for fixing bugs in some areas and so some parts are AI-written. However, the core functionality remains the same since our first version. 

Authors: Anango Prabhat, Thales Swanson
