from setuptools import setup

setup(
    name="elite-route-plotter",
    version="0.1.0",
    author="Joel Cressy (joel@jtcressy.net)",
    description="Plot routes throught neutron stars in Elite: Dangerous and send their system names to your console's text input",
    license="GPL",
    keywords="elite dangerous xbox one smartglass neutron router spansh.co.uk",
    url="https://github.com/jtcressy/elite-route-plotter",
    packages=[
        'elite_route_plotter'
    ],
    namespace_packages=[],
    zip_safe=False,
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Gamers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Topic :: Video Games :: Applications",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6"
    ],
    install_requires=[
        'xbox-smartglass-core',
        'wxpython',
        'tabulate'
    ],
    entry_points={
        'console_scripts': [
            'elite-route-plotter = elite_route_plotter.__main__:main []'
        ],
        'gui_scripts': [
            'elite-route-plotter = elite_route_plotter.__main__:main []'
        ]
    }
)
