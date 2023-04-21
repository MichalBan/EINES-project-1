# EINES-project-1

Postawienie infrastruktury: infrastructure.bash\
uruchomienie kontrolera: controller.bash\
sprzątanie: sudo mn -c

instrukcja uruchomienia:
1. zmienić w project_net.py adres kontrolera na adres lokalnej maszyny
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink,
                  controller=partial(RemoteController, ip='192.168.0.129', port=6633))
2. wrzucić project_controller.py i intent.txt do folderu pox
3. otworzyć terminal
4. stworzyć infrastrukturę: sudo ./infrastructure.bash
5. uruchomić kontroler: sudo ./controller.bash
