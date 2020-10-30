import codecs
import os
import re
import time
import urllib.request
import zipfile
from datetime import datetime
from shutil import copyfile

import PySimpleGUI as sg
from bs4 import BeautifulSoup
from pymongo import MongoClient

directoryList = 'http://thumbnailpacks.libretro.com/'


class ConsoleModel:
    name = ''
    link = ''
    filesize = 0
    date = datetime.min

    def __init__(self, name, link, date, filesize):
        self.name = name
        self.link = link
        self.date = date
        self.filesize = filesize

    def __str__(self):
        return self.name + ' - ' + self.link + ' - ' + str(self.date) + ' - ' + str(self.filesize) + 'kB'


def connect_to_db():
    client = MongoClient(
        'mongodb://ConsoleDBAdmin:m220password@cluster0-shard-00-00.kszyh.mongodb.net:27017,'
        'cluster0-shard-00-01.kszyh.mongodb.net:27017,cluster0-shard-00-02.kszyh.mongodb.net:'
        '27017/<dbname>?ssl=true&replicaSet=atlas-10oe5r-shard-0&authSource=admin&retryWrites=true&w=majority')
    return client.ConsoleDB
    # pprint(games_collection.find_one())


def download_zip(url):
    filename = urllib.parse.unquote(url.split('/')[-1])
    if os.path.exists(filename):
        print(filename + ' already exists')
        return
    urllib.request.urlretrieve(url, filename)


def unzip(file):
    with zipfile.ZipFile(file, 'r') as zip_ref:
        zip_ref.extractall(os.path.splitext(file)[0])


def find_matches(console_name):
    print(console_name)
    # Make console directory
    direc = 'images/' + console_name
    if not os.path.exists(direc):
        os.makedirs(direc)

    # DB Connection (find games with no boxart)
    db = connect_to_db()
    games_collection = db.games
    pipeline = [
        {
            '$match': {
                'console': console_name,
                'boxartUrl': {
                    '$exists': False
                }
            }
        }
    ]
    results = list(games_collection.aggregate(pipeline))
    print(len(results))

    # iterate through games
    for game in results:
        # find best match boxart -> snap -> title
        game_name = game['_name']
        filename = game_name + '.png'
        boxartpath = console_name + '/' + console_name + '/Named_Boxarts/' + filename
        snapspath = console_name + '/' + console_name + '/Named_Snaps/' + filename
        titlespath = console_name + '/' + console_name + '/Named_Titles/' + filename
        if os.path.exists(boxartpath):
            copyfile(boxartpath, direc + '/' + filename)
            db_upsert_one('games', {'_name': game_name}, 'boxartUrl', direc + '/' + filename)
        elif os.path.exists(snapspath):
            copyfile(snapspath, direc + '/' + filename)
            db_upsert_one('games', {'_name': game_name}, 'boxartUrl', direc + '/' + filename)
        elif os.path.exists(titlespath):
            copyfile(titlespath, direc + '/' + filename)
            db_upsert_one('games', {'_name': game_name}, 'boxartUrl', direc + '/' + filename)
        else:
            doc = open('error.log', 'w')
            doc.write("could not find art for: " + game_name + ' for console: ' + console_name)


def get_file_list():
    consoles = []
    directory_list_file = 'filelist.html'
    # localfilename, header = urllib.request.urlretrieve(directoryList, directoryListFile)
    document = open(directory_list_file, 'r')
    soup = BeautifulSoup(document, 'html.parser')
    itemlist = soup.find_all('a')
    itemlist.remove(itemlist[0])

    htmldoc = codecs.open(directory_list_file, 'r')
    text = htmldoc.read()

    date_list = re.findall(re.compile(r'\d{1,2}-.{3}-\d{4} \d{1,2}:\d{1,2}'), text)
    bytes_list = re.findall(re.compile(r'\d+\n'), text)

    for index, item in enumerate(itemlist):
        name = item.contents[0][:-4]
        link = directoryList + item.get('href')
        date = datetime.strptime(date_list[index], '%d-%b-%Y %H:%M')
        filesize = int(bytes_list[index]) / 1000
        consoles.append(ConsoleModel(name, link, date, filesize))
    document.close()
    return consoles


def artwork_gui():
    consoles = get_file_list()
    tabledata = []
    for console in consoles:
        tabledata += [[sg.Text(console.name.ljust(40)[:40], size=(40, 1)),
                       sg.Text(str(console.filesize).ljust(12)[:12] + 'kB', size=(20, 1)),
                       sg.Checkbox('', default=False, key=console)]]
    layout = [[sg.Text('Select systems to download:')]]
    layout += [[sg.Column(tabledata, scrollable=True, vertical_scroll_only=True, size=(500, 500))]]
    layout += [[sg.Button('Download'), sg.Button('Cancel')]]
    layout += [[sg.ProgressBar(len(consoles), orientation='h', size=(20, 20), key='progressbar')]]
    window = sg.Window('Artwork Downloader', layout)
    progress_bar = window['progressbar']
    while True:
        event, console_selection = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel':  # if user closes window or clicks cancel
            break
        if event == 'Download':
            console_dl_list = []
            totalsize = 0
            for console, sel in console_selection.items():
                if sel:
                    totalsize += console.filesize
                    console_dl_list.append(console)
            progress_bar.UpdateBar(0, len(console_dl_list))
            print('Selected list: ' + str(len(console_dl_list)) + ' x ' + str(totalsize.__round__()) + 'kB / ' + str(
                totalsize.__round__() / 1000) + 'mB / ' + str(totalsize.__round__() / 1000000) + 'gB')

            response = sg.PopupOKCancel(
                'Are you sure you wish to proceed \n Total download size: ' + str(totalsize.__round__() / 1000) + 'mB',
                title='Confirm', )
            if response == 'OK':
                for index, console in enumerate(console_dl_list):
                    download_zip(console.link)
                    progress_bar.UpdateBar(index)
            else:
                print('cancel')


def get_downloads():
    filelist = []
    for file in os.listdir():
        if file.lower().endswith('zip'):
            filelist.append(file)
    return filelist


def unpack_gui():
    filelist = get_downloads()

    tabledata = []
    for file in filelist:
        checked = True
        if os.path.exists(os.path.splitext(file)[0]):
            checked = False
        tabledata += [
            [sg.Text(file, size=(40, 1)), sg.Text(str(round(os.path.getsize(file) / 1000 / 1000)) + 'mB', size=(20, 1)),
             sg.Checkbox('', default=checked, key=file)]]
    layout = [[sg.Text('Select systems to unpack:')]]
    layout += [[sg.Column(tabledata, scrollable=True, vertical_scroll_only=True, size=(500, 500))]]
    layout += [[sg.Button('Unpack'), sg.Button('Cancel')]]
    layout += [[sg.ProgressBar(len(filelist), orientation='h', size=(20, 20), key='progressbar')]]
    window = sg.Window('Artwork Downloader', layout)
    progress_bar = window['progressbar']
    while True:
        event, file_selection = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel':  # if user closes window or clicks cancel
            break
        if event == 'Unpack':
            console_unpack_list = []
            totalsize = 0
            for file, sel in file_selection.items():
                if sel:
                    totalsize += os.path.getsize(file) / 1000
                    console_unpack_list.append(file)
            progress_bar.UpdateBar(0, len(console_unpack_list))
            print('Selected list: ' + str(len(console_unpack_list)) + ' x ' + str(round(totalsize)) + 'kB / ' + str(
                round(totalsize) / 1000) + 'mB / ' + str(round(totalsize) / 1000000) + 'gB')

            response = sg.PopupOKCancel('Are you sure you wish to proceed \n Total compressed file size: ' + str(
                round(totalsize) / 1000) + 'mB', title='Confirm', )
            if response == 'OK':
                for index, file in enumerate(console_unpack_list):
                    unzip(file)
                    time.sleep(1)
                    progress_bar.UpdateBar(index)
                progress_bar.len(console_unpack_list)
                sg.PopupOK('Unzip Complete')
            else:
                print('cancel')


def db_insert_one(collection, document):
    db = connect_to_db()
    current_collection = db[collection]
    res = current_collection.insert_one(document)
    sg.PopupOK('Database returned:' + str(res))


def db_insert_many(collection, documents):
    db = connect_to_db()
    current_collection = db[collection]
    res = current_collection.insert_many(documents)
    sg.PopupOK('Database returned:' + str(res))


def db_update_many(collection, filt, field, value):
    db = connect_to_db()
    current_collection = db[collection]
    res = current_collection.update_many(filt, {'$set': {field: value}})
    sg.PopupOK('Database returned:' + str(res.modified_count))


def db_upsert_one(collection, filt, field, value):
    db = connect_to_db()
    current_collection = db[collection]
    res = current_collection.update_one(filt, {'$set': {field: value}}, upsert=True)
    print('Database returned:' + str(res.modified_count))


def match_artwork():
    # For each directory (console name)
    for direc in os.listdir('../../.config/JetBrains/PyCharmCE2020.2/scratches/'):
        if os.path.isdir(direc):
            find_matches(direc)


def custom_update(console_name):
    db = connect_to_db()
    current_collection = db['consoles']
    filt = {
        'name': console_name,
        'logoUrl': ''}
    res = current_collection.update_one(filt,
                                        {'$set': {'logoUrl': 'images/' + console_name + '/' + console_name + '.png'}})
    sg.PopupOK('Database returned:' + str(res.modified_count))


def update_db_gui():
    layout = [[sg.Button('Add Consoles')],
              [sg.Button('Add Games')],
              # [sg.Button('Update Date Format', key='dates')],
              [sg.Button('Update Details', key='update')],
              [sg.Button('Artwork Matcher', key='art')], ]
    window = sg.Window('Console DB Utils', layout)
    while True:
        event, selection = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel':  # if user closes window or clicks cancel
            break
        if event == 'Add Consoles':
            result = sg.PopupGetFile('Select ZIP file to import consoles', multiple_files=True,
                                     file_types=(('ZIP files', '*.zip'),))
            files = result.split(';')
            if files is not None:
                console_list = []
                for file in files:
                    filename = os.path.basename(file)
                    brand = os.path.splitext(filename)[0].split('-')[0].strip()
                    name = os.path.splitext(filename)[0].split('-')[1].strip()
                    console = {
                        'name': str(name),
                        'version': datetime.now(),
                        'date': datetime.now(),
                        'brand': brand,
                        'logoUrl': '',
                        'photoUrl': '',
                        'year': '0000',
                        'description': brand + ' - ' + name}
                    console_list.append(console)
                db_insert_many('consoles', console_list)
        if event == 'Add Games':
            files = sg.PopupGetFile('Select DAT file to import games', initial_folder='/home/matt/Documents/dats',
                                    file_types=(('DAT files', '*.dat'),))
            print('add games')
        if event == 'dates':
            db_update_many(collection='consoles', field='date', value=datetime.now())
        if event == 'art':
            match_artwork()
        if event == 'update':  # Update console name (disabled)
            custom_update('Atari 2600')


def main_menu():
    layout = [[sg.Button('Artwork Download', key='Artwork')],
              [sg.Button('Unpack Resources', key='Unpack')],
              [sg.Button('Update Database', key='UpdateDB')]]
    window = sg.Window('Console DB Utils', layout)
    while True:
        event, selection = window.read()
        if event == sg.WIN_CLOSED or event == 'Cancel':  # if user closes window or clicks cancel
            break
        if event == 'Artwork':
            artwork_gui()
        if event == 'Unpack':
            unpack_gui()
        if event == 'UpdateDB':
            update_db_gui()
    window.close()


# main_menu()


update_db_gui()
