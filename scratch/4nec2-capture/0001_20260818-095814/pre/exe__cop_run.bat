rem
rem	Batch file for copying 4nec2 run-time files.
rem

rem	runtime:

	set dest=C:\4nec2

	copy _Info.txt		%dest%
	copy _ReadMeFirst.txt	%dest%
	copy _GetStarted.txt	%dest%
	copy _out_of_env_space.txt %dest%
	copy _Run_Dos_problem.txt %dest%
	copy cards.rtf		%dest%
	copy nec2.doc		%dest%
	pause

rem 	copy 4nec2.ini 		%dest%\exe
 	copy smith.dat 		%dest%\exe
 	copy smith1.dat		%dest%\exe
	copy sect.gif		%dest%\exe
	copy stubP.gif		%dest%\exe
	copy stubS.gif		%dest%\exe
	copy Gnd.bmp		%dest%\exe
	pause

	copy 4nec2.chm 		%dest%\exe
	copy 4nec2.hlp 		%dest%\exe
	copy 4nec2.cnt 		%dest%\exe
	copy 4nec2.rtf 		%dest%\exe
	copy 4nec2.exe 		%dest%\exe
	copy 4nec2.bat 		%dest%\exe
	copy 4nec2.pif 		%dest%\exe
	copy nec4.bat 		%dest%\exe
	pause

rem 	copy symbols.txt 	%dest%\exe
rem 	copy sunspot.txt 	%dest%\exe
rem 	copy coax.txt 		%dest%\exe
rem	copy edit2.txt		%dest%\exe
rem	copy edit4.txt		%dest%\exe
rem	copy color0.dat 	%dest%\exe
rem	copy default.pov	%dest%\exe

	copy ..\data\*.* 	%dest%\data
	pause

	copy ..\its\*.* 		%dest%\its
	copy ..\its\receive\*.* 	%dest%\its\receive
	copy ..\its\transmit\*.* 	%dest%\its\transmit
	pause

	copy view.hlp		%dest%\exe
	copy view.rtf		%dest%\exe
	copy view.exe		%dest%\exe
	copy view.ini		%dest%\exe

	copy build.hlp		%dest%\exe
	copy build.rtf		%dest%\exe
	copy build.exe		%dest%\exe
	copy build.ini		%dest%\exe
	
	copy box.gif		%dest%\exe
	copy cylinder.gif	%dest%\exe
	copy helix.gif		%dest%\exe
	copy parabola.gif	%dest%\exe
	copy parabola1.gif	%dest%\exe
	copy parabola2.gif	%dest%\exe
	copy patch.gif		%dest%\exe
	copy plane.gif		%dest%\exe
	copy sphere.gif		%dest%\exe

	copy itsutil.exe	%dest%\exe
	copy itsutil.ini	%dest%\exe
	copy itsutil.html	%dest%\exe
	copy itscontour.html	%dest%\exe
	copy itsscaling.html	%dest%\exe
	pause

	copy F77L3.eer 		%dest%\exe

	copy nec2d.exe 		%dest%\exe
	copy nec2d512.exe 	%dest%\exe
	copy nec2d960.exe 	%dest%\exe
	copy nec2d1k4.exe 	%dest%\exe
	copy somnec2d.exe 	%dest%\exe

	copy nec2dxs500.exe 	%dest%\exe
	copy nec2dxs1k5.exe 	%dest%\exe
	copy nec2dxs3k0.exe 	%dest%\exe
	copy nec2dxs5k0.exe 	%dest%\exe
	copy nec2dxs8k0.exe 	%dest%\exe
	copy nec2dxs11k.exe 	%dest%\exe

	copy getdxver.exe	%dest%\exe
	copy convert.exe	%dest%\exe
	pause

	copy cop_run.bat	%dest%\exe
	copy cop_runX.bat	%dest%\exe

