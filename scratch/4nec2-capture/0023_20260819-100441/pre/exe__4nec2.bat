@echo off
if "%3" == "" echo on

set nec2d=%2.exe
set som2d=somnec2d.exe
if "%2" == "" set nec2d=nec2d.exe

if "%1" == "gen" goto gen
chdir exe
type som2d.tmp
%som2d% < som2d.tmp
if "%3" == "" pause
chdir ..

:gen
chdir exe
type nec2d.tmp
%nec2d% < nec2d.tmp
if "%3" == "" pause
chdir ..