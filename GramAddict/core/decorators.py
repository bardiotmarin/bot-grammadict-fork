

import logging
import sys
import traceback
from datetime import datetime
from http.client import HTTPException
from socket import timeout

from colorama import Fore, Style
import requests.exceptions
from adbutils.errors import AdbError
from uiautomator2.exceptions import UiObjectNotFoundError

from GramAddict.core.device_facade import DeviceFacade
from GramAddict.core.report import print_full_report
from GramAddict.core.utils import (
    EmptyList,
    check_if_crash_popup_is_there,
    close_instagram,
    open_instagram,
    random_sleep,
    save_crash,
    stop_bot,
)
from GramAddict.core.views import TabBarView

logger = logging.getLogger(__name__)


def run_safely(device, device_id, sessions, session_state, screen_record, configs):
    def actual_decorator(func):
        def wrapper(*args, **kwargs):
            session_state = sessions[-1]
            try:
                func(*args, **kwargs)
            except KeyboardInterrupt:
                try:
                    # Catch Ctrl-C and ask if user wants to pause execution
                    logger.info(
                        "CTRL-C detected . . .",
                        extra={"color": f"{Style.BRIGHT}{Fore.YELLOW}"},
                    )
                    logger.info(
                        f"-------- PAUSED: {datetime.now().strftime('%H:%M:%S')} --------",
                        extra={"color": f"{Style.BRIGHT}{Fore.YELLOW}"},
                    )
                    logger.info(
                        "NOTE: This is a rudimentary pause. It will restart the action, while retaining session data.",
                        extra={"color": Style.BRIGHT},
                    )
                    logger.info(
                        "Press RETURN to resume or CTRL-C again to Quit: ",
                        extra={"color": Style.BRIGHT},
                    )

                    input("")

                    logger.info(
                        f"-------- RESUMING: {datetime.now().strftime('%H:%M:%S')} --------",
                        extra={"color": f"{Style.BRIGHT}{Fore.YELLOW}"},
                    )
                    TabBarView(device).navigateToProfile()
                except KeyboardInterrupt:
                    stop_bot(device, sessions, session_state)

            except DeviceFacade.AppHasCrashed:
                logger.warning("App has crashed / has been closed!")
                restart(
                    device,
                    sessions,
                    session_state,
                    configs,
                    normal_crash=False,
                    print_traceback=False,
                )

            except (
                DeviceFacade.JsonRpcError,
                IndexError,
                HTTPException,
                timeout,
                UiObjectNotFoundError,
                EmptyList,
                # Erreurs de communication avec atx-agent dans l'emulateur.
                # Elles sont TRANSITOIRES : uiautomator2 se repare tout seul
                # ("atx-agent has something wrong, auto recovering" puis
                # "device is online"). Sans cette ligne elles tombaient dans le
                # "except Exception" plus bas, qui tue la session alors que la
                # connexion revenait 3 secondes plus tard.
                # RequestException couvre ConnectionError, ConnectTimeout et
                # ReadTimeout. Le nombre de redemarrages reste borne par
                # total-crashes-limit, donc pas de boucle infinie.
                requests.exceptions.RequestException,
                # Perte du transport adb vers la VM ("AdbError: closed",
                # "AdbTimeout", ... -- AdbError est la classe de base des trois
                # erreurs d'adbutils). C'est le pendant, une couche plus bas, de
                # RequestException ci-dessus : quand le transport tombe, le port
                # forwarde vers atx-agent meurt avec lui, donc uiautomator2
                # echoue en HTTP PUIS en adb. Sa reparation automatique
                # (_setup_atx_agent) passe elle-meme par adb et levait cette
                # erreur depuis le chemin de secours, ce qui tombait dans le
                # "except Exception" plus bas et tuait la session alors que la
                # VM etait toujours la. Borne par total-crashes-limit.
                AdbError,
            ):
                restart(
                    device,
                    sessions,
                    session_state,
                    configs,
                )

            except Exception as e:
                logger.error(traceback.format_exc())
                for exception_line in traceback.format_exception_only(type(e), e):
                    logger.critical(
                        f"'{exception_line}' -> This kind of exception will stop the bot (no restart)."
                    )
                logger.info(
                    f"List of running apps: {', '.join(device.deviceV2.app_list_running())}"
                )
                save_crash(device)
                close_instagram(device)
                print_full_report(sessions, configs.args.scrape_to_file)
                sessions.persist(directory=session_state.my_username)
                raise e from e

        return wrapper

    return actual_decorator


def restart(
    device: DeviceFacade,
    sessions,
    session_state,
    configs,
    normal_crash: bool = True,
    print_traceback: bool = True,
):
    if print_traceback:
        logger.error(traceback.format_exc())
        # save_crash() prend une capture et un dump via le device : sur un
        # transport mort il leve AdbError (il ne rattrape que RuntimeError).
        # Leve DEPUIS un bloc except, l'erreur ne serait plus rattrapee par
        # personne et tuerait la session que l'on est justement en train de
        # recuperer. Un diagnostic manquant ne doit jamais couter la session.
        try:
            save_crash(device)
        except Exception as diag_error:
            logger.warning(f"Impossible de sauvegarder le crash: {diag_error}")
    try:
        logger.info(
            f"List of running apps: {', '.join(device.deviceV2.app_list_running())}."
        )
    except Exception as diag_error:
        logger.warning(f"Liste des apps indisponible: {diag_error}")
    if configs.args.count_app_crashes or normal_crash:
        session_state.totalCrashes += 1
        if session_state.check_limit(
            limit_type=session_state.Limit.CRASHES, output=True
        ):
            logger.error(
                "Reached crashes limit. Bot has crashed too much! Please check what's going on."
            )
            stop_bot(device, sessions, session_state)
        logger.info("Something unexpected happened. Let's try again.")
    close_instagram(device)
    check_if_crash_popup_is_there(device)
    random_sleep()
    if not open_instagram(device):
        print_full_report(sessions, configs.args.scrape_to_file)
        sessions.persist(directory=session_state.my_username)
        sys.exit(2)
    TabBarView(device).navigateToProfile()
